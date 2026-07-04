"""
Py2APK – Tornado application entry point.

Starts the HTTP server, registers all routes, initialises the database,
and schedules the periodic cleanup task.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import tornado.ioloop
import tornado.web
from tornado.ioloop import PeriodicCallback

from app.config import config
from app.database import init_db
from app.handlers.auth import LoginHandler, LogoutHandler, RegisterHandler
from app.handlers.base import BaseHandler
from app.handlers.build import (
    BuildCancelHandler,
    BuildDeleteHandler,
    BuildRetryHandler,
    BuildStartHandler,
    BuildStatusHandler,
)
from app.handlers.download import APKDownloadHandler
from app.handlers.logs import BuildLogsDownloadHandler, BuildLogsJSONHandler, BuildLogsWSHandler
from app.handlers.pages import (
    BuildListAPIHandler,
    BuildPageHandler,
    DownloadPageHandler,
    HistoryPageHandler,
    HomeHandler,
    SettingsPageHandler,
    StatsAPIHandler,
    UploadPageHandler,
)
from app.handlers.upload import UploadHandler
from app.utils.cleanup import run_cleanup

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("py2apk")

BASE_DIR = Path(__file__).parent.parent


# ── 404 handler ───────────────────────────────────────────────────────────────

class NotFoundHandler(BaseHandler):
    def prepare(self):
        raise tornado.web.HTTPError(404, "Page not found")


# ── Application factory ───────────────────────────────────────────────────────

def make_app() -> tornado.web.Application:
    # Ensure all data directories exist
    for d in (config.UPLOAD_DIR, config.BUILD_DIR, config.APK_DIR, config.ICON_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)

    settings = {
        "debug": config.DEBUG,
        "template_path": str(BASE_DIR / "templates"),
        "static_path": str(BASE_DIR / "static"),
        "static_url_prefix": "/static/",
        "cookie_secret": config.SECRET_KEY,
        "login_url": "/login",
        "xheaders": True,          # trust X-Forwarded-For / X-Real-IP from proxy
        "compress_response": True,
        "default_handler_class": NotFoundHandler,
        "autoescape": "xhtml_escape",
    }

    routes = [
        # ── Pages ────────────────────────────────────────────────────────────
        (r"/",                        HomeHandler),
        (r"/upload",                  UploadPageHandler),
        (r"/builds/([^/]+)",          BuildPageHandler),
        (r"/download/([^/]+)",        DownloadPageHandler),
        (r"/history",                 HistoryPageHandler),
        (r"/settings",                SettingsPageHandler),
        (r"/login",                   LoginHandler),
        (r"/logout",                  LogoutHandler),
        (r"/register",                RegisterHandler),

        # ── REST API ──────────────────────────────────────────────────────────
        (r"/api/upload",                          UploadHandler),
        (r"/api/builds",                          BuildListAPIHandler),
        (r"/api/builds/([^/]+)/start",            BuildStartHandler),
        (r"/api/builds/([^/]+)/cancel",           BuildCancelHandler),
        (r"/api/builds/([^/]+)/retry",            BuildRetryHandler),
        (r"/api/builds/([^/]+)/status",           BuildStatusHandler),
        (r"/api/builds/([^/]+)/download",         APKDownloadHandler),
        (r"/api/builds/([^/]+)/logs/json",         BuildLogsJSONHandler),
        (r"/api/builds/([^/]+)/logs",             BuildLogsDownloadHandler),
        (r"/api/builds/([^/]+)",                  BuildDeleteHandler),
        (r"/api/stats",                           StatsAPIHandler),

        # ── WebSocket ─────────────────────────────────────────────────────────
        (r"/ws/builds/([^/]+)/logs",              BuildLogsWSHandler),
    ]

    return tornado.web.Application(routes, **settings)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("Starting Py2APK on %s:%d", config.HOST, config.PORT)

    init_db()

    app = make_app()
    app.listen(
        config.PORT,
        address=config.HOST,
        max_buffer_size=config.MAX_UPLOAD_SIZE + 10 * 1024 * 1024,
        max_body_size=config.MAX_UPLOAD_SIZE + 10 * 1024 * 1024,
    )

    # Schedule periodic cleanup
    cleanup_cb = PeriodicCallback(run_cleanup, config.CLEANUP_INTERVAL * 1000)
    cleanup_cb.start()

    logger.info("Py2APK ready → http://%s:%d", config.HOST, config.PORT)
    await asyncio.Event().wait()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
