"""
APK download handler.
GET /api/builds/{id}/download
"""

import logging
import os

import tornado.web

from app.handlers.base import BaseHandler
from app.models.build import get_build

logger = logging.getLogger(__name__)


class APKDownloadHandler(BaseHandler):
    async def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        if build["status"] != "success":
            self.write_error_json(
                f"APK not ready. Build status is '{build['status']}'.", 409
            )
            return

        apk_path = build.get("apk_path")
        if not apk_path or not os.path.isfile(apk_path):
            self.write_error_json("APK file not found on server.", 404)
            return

        filename = os.path.basename(apk_path)
        file_size = os.path.getsize(apk_path)

        self.set_header("Content-Type", "application/vnd.android.package-archive")
        self.set_header(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        self.set_header("Content-Length", str(file_size))

        logger.info("Serving APK %s for build %s", filename, build_id)

        # Stream in 64 KB chunks to avoid loading the whole file into RAM
        with open(apk_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.write(chunk)
                await self.flush()
