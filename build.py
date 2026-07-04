"""
Build management handlers.
POST  /api/builds/{id}/start    – start a build
POST  /api/builds/{id}/cancel   – cancel (kill container)
POST  /api/builds/{id}/retry    – re-queue a failed build
GET   /api/builds/{id}/status   – JSON build status
DELETE /api/builds/{id}          – delete build + files
"""

import asyncio
import logging
import os
import shutil

import tornado.web

from app.config import config
from app.handlers.base import BaseHandler
from app.models.build import (
    delete_build,
    get_build,
    get_logs,
    update_build_status,
)
from app.utils.docker_builder import build_queue

logger = logging.getLogger(__name__)


class BuildStartHandler(BaseHandler):
    async def post(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        if build["status"] not in ("pending", "failed"):
            self.write_error_json(
                f"Cannot start a build with status '{build['status']}'.", 409
            )
            return

        if not build.get("upload_path") or not os.path.isfile(build["upload_path"]):
            self.write_error_json("Upload file not found; please upload again.", 400)
            return

        # Fire-and-forget in the asyncio event loop
        asyncio.ensure_future(
            build_queue.submit(
                build_id,
                upload_path=build["upload_path"],
                app_name=build["app_name"],
                package_name=build["package_name"],
                version_name=build["version_name"],
                version_code=build["version_code"],
                icon_path=build.get("icon_path") or None,
                splash_path=build.get("splash_path") or None,
                email=build.get("email_notification") or None,
            )
        )

        self.write_json({"build_id": build_id, "status": "queued"})


class BuildStatusHandler(BaseHandler):
    async def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        # Strip internal paths from public response
        safe = dict(build)
        for key in ("upload_path", "docker_container_id"):
            safe.pop(key, None)
        if safe.get("apk_path"):
            safe["apk_filename"] = os.path.basename(safe["apk_path"])

        self.write_json(safe)


class BuildCancelHandler(BaseHandler):
    async def post(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        if build["status"] not in ("pending", "queued", "building"):
            self.write_error_json(
                f"Cannot cancel a build with status '{build['status']}'.", 409
            )
            return

        # Kill the Docker container if it's running
        container_id = build.get("docker_container_id")
        if container_id:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "kill", container_id,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception as e:
                logger.warning("Could not kill container %s: %s", container_id, e)

        update_build_status(build_id, "cancelled", error_message="Cancelled by user.")
        self.write_json({"build_id": build_id, "status": "cancelled"})


class BuildRetryHandler(BaseHandler):
    async def post(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        if build["status"] not in ("failed", "cancelled"):
            self.write_error_json(
                f"Only failed or cancelled builds can be retried.", 409
            )
            return

        if not build.get("upload_path") or not os.path.isfile(build["upload_path"]):
            self.write_error_json("Original upload no longer available; please upload again.", 400)
            return

        update_build_status(build_id, "pending", error_message=None, apk_path=None)

        asyncio.ensure_future(
            build_queue.submit(
                build_id,
                upload_path=build["upload_path"],
                app_name=build["app_name"],
                package_name=build["package_name"],
                version_name=build["version_name"],
                version_code=build["version_code"],
                icon_path=build.get("icon_path") or None,
                splash_path=build.get("splash_path") or None,
                email=build.get("email_notification") or None,
            )
        )

        self.write_json({"build_id": build_id, "status": "queued"})


class BuildDeleteHandler(BaseHandler):
    async def delete(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        if build["status"] in ("building", "queued"):
            self.write_error_json("Cannot delete a build that is currently running.", 409)
            return

        # Remove associated files
        for path_key in ("upload_path", "icon_path"):
            p = build.get(path_key)
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

        apk_dir = os.path.join(config.APK_DIR, build_id)
        if os.path.isdir(apk_dir):
            shutil.rmtree(apk_dir, ignore_errors=True)

        delete_build(build_id)
        self.write_json({"deleted": build_id})
