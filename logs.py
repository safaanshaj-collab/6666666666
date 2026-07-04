"""
Real-time build log streaming via WebSocket.
WS  /ws/builds/{id}/logs        – stream new log lines
GET /api/builds/{id}/logs       – download full log as plain text
GET /api/builds/{id}/logs/json  – incremental JSON log lines (used by WS fallback)
"""

import json
import logging

import tornado.websocket

from app.config import config
from app.handlers.base import BaseHandler
from app.models.build import get_build, get_logs

logger = logging.getLogger(__name__)

# Keep a registry of open WebSocket connections per build_id
# so the docker_builder can push updates in real time.
_ws_clients: dict[str, set["BuildLogsWSHandler"]] = {}


def broadcast_log(build_id: str, log_entry: dict) -> None:
    """Called by other parts of the app to push a new log line."""
    for client in list(_ws_clients.get(build_id, set())):
        try:
            client.write_message(json.dumps(log_entry))
        except Exception:
            pass


class BuildLogsWSHandler(tornado.websocket.WebSocketHandler):
    """
    WebSocket handler for streaming build logs.

    Protocol (server → client):
      { "type": "log",    "id": <int>, "ts": "...", "level": "INFO", "message": "..." }
      { "type": "status", "status": "success"|"failed"|"cancelled" }
      { "type": "ping" }

    The client sends nothing; the connection is read-only push.
    """

    def initialize(self) -> None:
        self.build_id: str = ""
        self._last_id: int = 0
        self._poll_handle = None

    def check_origin(self, origin: str) -> bool:
        # Origin verification is handled at the Nginx/proxy layer.
        # We still enforce auth via get_current_user in open().
        return True

    def get_current_user(self):
        """WebSocketHandler doesn't call prepare(), so we check auth here."""
        if not config.ENABLE_AUTH:
            return {"id": None, "username": "guest", "is_admin": True}
        from app.database import get_db
        user_id = self.get_secure_cookie("user_id")
        if not user_id:
            return None
        try:
            db = get_db()
            row = db.execute(
                "SELECT id, username, email, is_admin FROM users WHERE id=?",
                (int(user_id),),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    async def open(self, build_id: str) -> None:
        # ── Auth check ────────────────────────────────────────────────────
        if config.ENABLE_AUTH and not self.current_user:
            self.close(4401, "Authentication required")
            return

        self.build_id = build_id
        build = get_build(build_id)
        if not build:
            self.close(1008, "Build not found")
            return

        # ── Owner / admin check ───────────────────────────────────────────
        if config.ENABLE_AUTH:
            user = self.current_user
            if not user.get("is_admin"):
                owner_id = build.get("user_id")
                if owner_id is None or owner_id != user.get("id"):
                    self.close(4403, "Access denied")
                    return

        # Register this connection
        _ws_clients.setdefault(build_id, set()).add(self)

        # Send all existing logs immediately
        existing = get_logs(build_id, after_id=0)
        for entry in existing:
            self.write_message(
                json.dumps({
                    "type": "log",
                    "id": entry["id"],
                    "ts": entry["ts"],
                    "level": entry["level"],
                    "message": entry["message"],
                })
            )
            self._last_id = entry["id"]

        # If the build is already finished, send the status and close
        if build["status"] in ("success", "failed", "cancelled"):
            self.write_message(json.dumps({"type": "status", "status": build["status"]}))
            self.close()
            return

        # Start polling for new logs (the Docker runner writes to DB)
        self._start_polling()

    def _start_polling(self) -> None:
        from tornado.ioloop import IOLoop, PeriodicCallback

        def _poll():
            if self.ws_connection is None:
                return
            try:
                new_entries = get_logs(self.build_id, after_id=self._last_id)
                for entry in new_entries:
                    self.write_message(
                        json.dumps({
                            "type": "log",
                            "id": entry["id"],
                            "ts": entry["ts"],
                            "level": entry["level"],
                            "message": entry["message"],
                        })
                    )
                    self._last_id = entry["id"]

                # Check if the build has finished
                build = get_build(self.build_id)
                if build and build["status"] in ("success", "failed", "cancelled"):
                    self.write_message(
                        json.dumps({"type": "status", "status": build["status"]})
                    )
                    self.close()
            except Exception as e:
                logger.warning("Log poll error for %s: %s", self.build_id, e)

        self._poll_handle = PeriodicCallback(_poll, 1000)  # every 1 second
        self._poll_handle.start()

    def on_close(self) -> None:
        if self._poll_handle:
            self._poll_handle.stop()
        _ws_clients.get(self.build_id, set()).discard(self)


class BuildLogsDownloadHandler(BaseHandler):
    """Download the full build log as plain text."""

    async def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        entries = get_logs(build_id)
        lines = [f"[{e['ts']}] [{e['level']:7s}] {e['message']}" for e in entries]
        text = "\n".join(lines)

        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.set_header(
            "Content-Disposition",
            f'attachment; filename="build-{build_id[:8]}.log"',
        )
        self.write(text)


class BuildLogsJSONHandler(BaseHandler):
    """
    Incremental JSON log lines for the WebSocket polling fallback.
    GET /api/builds/{id}/logs/json?after=<last_log_id>

    Returns:
      { "logs": [ { "id": int, "ts": str, "level": str, "message": str }, … ],
        "status": "building" | "success" | … }
    """

    async def get(self, build_id: str):
        build = get_build(build_id)
        if not build:
            self.write_error_json("Build not found.", 404)
            return
        self.check_build_access(build)

        try:
            after_id = int(self.get_argument("after", "0"))
        except ValueError:
            after_id = 0

        entries = get_logs(build_id, after_id=after_id)
        self.write_json({
            "logs": [dict(e) for e in entries],
            "status": build["status"],
        })
