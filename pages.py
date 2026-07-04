"""
HTML page handlers and REST list/stats endpoints.
"""

import logging

import tornado.web

from app.config import config
from app.handlers.base import BaseHandler
from app.models.build import get_build, get_stats, list_builds

logger = logging.getLogger(__name__)


# ── Page handlers ─────────────────────────────────────────────────────────────

class HomeHandler(BaseHandler):
    def get(self):
        stats = get_stats()
        recent, _ = list_builds(page=1, page_size=5)
        self.render(
            "index.html",
            title="Dashboard",
            stats=stats,
            recent_builds=recent,
        )


class UploadPageHandler(BaseHandler):
    def get(self):
        self.render("upload.html", title="New Build")


class BuildPageHandler(BaseHandler):
    def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            raise tornado.web.HTTPError(404, "Build not found")
        self.render("build.html", title=f"Build {build_id[:8]}", build=build)


class DownloadPageHandler(BaseHandler):
    def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            raise tornado.web.HTTPError(404, "Build not found")
        if build["status"] != "success":
            self.redirect(f"/builds/{build_id}")
            return
        self.render("download.html", title="Download APK", build=build)


class HistoryPageHandler(BaseHandler):
    def get(self):
        self.render("history.html", title="Build History")


class SettingsPageHandler(BaseHandler):
    def get(self):
        self.render(
            "settings.html",
            title="Settings",
            config=config,
        )


# ── REST: build list + stats ──────────────────────────────────────────────────

class BuildListAPIHandler(BaseHandler):
    async def get(self):
        try:
            page = max(1, int(self.get_argument("page", "1")))
        except ValueError:
            page = 1
        page_size = min(100, max(1, int(self.get_argument("page_size", str(config.PAGE_SIZE)))))
        status = self.get_argument("status", "")
        search = self.get_argument("search", "")

        user = self.current_user
        user_id = user.get("id") if user and not user.get("is_admin") else None

        builds, total = list_builds(
            page=page,
            page_size=page_size,
            status=status,
            search=search,
            user_id=user_id,
        )

        # Strip internal paths
        for b in builds:
            b.pop("upload_path", None)
            b.pop("docker_container_id", None)
            import os
            if b.get("apk_path"):
                b["apk_filename"] = os.path.basename(b["apk_path"])

        self.write_json(
            {
                "builds": builds,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size,
            }
        )


class StatsAPIHandler(BaseHandler):
    async def get(self):
        self.write_json(get_stats())
