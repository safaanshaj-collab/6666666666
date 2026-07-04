"""
Base Tornado request handler with shared helpers.
"""

import json
import logging
from typing import Any, Optional

import tornado.web

from app.config import config
from app.database import get_db

logger = logging.getLogger(__name__)


class BaseHandler(tornado.web.RequestHandler):
    """All page and API handlers extend this class."""

    # ── JSON helpers ─────────────────────────────────────────────────────────

    def write_json(self, data: Any, status: int = 200) -> None:
        self.set_status(status)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(json.dumps(data, default=str))

    def write_error_json(self, message: str, status: int = 400) -> None:
        self.write_json({"error": message}, status=status)

    # ── Request body ──────────────────────────────────────────────────────────

    def get_json_body(self) -> Optional[dict]:
        try:
            return json.loads(self.request.body)
        except Exception:
            return None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def get_current_user(self) -> Optional[dict]:
        if not config.ENABLE_AUTH:
            return {"id": None, "username": "guest", "is_admin": True}
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

    # ── Template context ──────────────────────────────────────────────────────

    def get_template_namespace(self) -> dict:
        ns = super().get_template_namespace()
        ns["current_user"] = self.current_user
        ns["enable_auth"] = config.ENABLE_AUTH
        return ns

    # ── Error pages ───────────────────────────────────────────────────────────

    def write_error(self, status_code: int, **kwargs) -> None:
        message = self._reason
        if "exc_info" in kwargs:
            import traceback
            exc = kwargs["exc_info"][1]
            if config.DEBUG:
                message = traceback.format_exc()
            else:
                message = str(exc) if str(exc) else self._reason

        if self.request.path.startswith("/api/") or self.request.path.startswith("/ws/"):
            self.write_json({"error": message}, status=status_code)
        else:
            self.render(
                "error.html",
                status_code=status_code,
                message=message,
                title=f"Error {status_code}",
            )

    def check_build_access(self, build: dict) -> None:
        """Raise 403 if the current user is not the build owner or an admin.

        Call this in any handler that retrieves a build by ID to prevent IDOR.
        When auth is disabled every request acts as admin, so no restriction applies.
        """
        if not config.ENABLE_AUTH:
            return
        user = self.current_user
        if not user:
            raise tornado.web.HTTPError(401, "Authentication required")
        if user.get("is_admin"):
            return
        owner_id = build.get("user_id")
        if owner_id is None or owner_id != user.get("id"):
            raise tornado.web.HTTPError(403, "Access denied to this build")

    def prepare(self) -> None:
        """Enforce auth on all non-static routes."""
        if not config.ENABLE_AUTH:
            return
        excluded = {"/login", "/api/auth/login", "/api/auth/register"}
        if self.request.path in excluded or self.request.path.startswith("/static/"):
            return
        if not self.current_user:
            if self.request.path.startswith("/api/") or self.request.path.startswith("/ws/"):
                raise tornado.web.HTTPError(401, "Authentication required")
            self.redirect("/login")
