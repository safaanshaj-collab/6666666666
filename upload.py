"""
File upload handler with validation and security scanning.
POST /api/upload
"""

import logging
import os
from pathlib import Path

import tornado.web

from app.config import config
from app.handlers.base import BaseHandler
from app.models.build import create_build
from app.utils.security import SecurityError, safe_filename, validate_upload

logger = logging.getLogger(__name__)


class UploadHandler(BaseHandler):
    """
    Accepts a multipart/form-data POST with:
      file          – the .py or .zip file (required)
      app_name      – human-readable app name  (optional, default 'MyApp')
      package_name  – Android package name     (optional)
      version_name  – semantic version string  (optional, default '1.0')
      version_code  – integer version          (optional, default 1)
      icon          – PNG icon file            (optional)
      email         – notification email       (optional)
    """

    async def post(self):
        # ── File presence ────────────────────────────────────────────────────
        files = self.request.files.get("file")
        if not files:
            self.write_error_json("No file uploaded.", 400)
            return

        file_info = files[0]
        original_name = file_info["filename"] or "upload"
        body = file_info["body"]

        # ── Size check ───────────────────────────────────────────────────────
        if len(body) > config.MAX_UPLOAD_SIZE:
            limit_mb = config.MAX_UPLOAD_SIZE // (1024 * 1024)
            self.write_error_json(f"File exceeds the {limit_mb} MB size limit.", 413)
            return

        # ── Form fields ──────────────────────────────────────────────────────
        app_name = self.get_argument("app_name", "MyApp").strip() or "MyApp"
        package_name = (
            self.get_argument("package_name", "org.example.myapp").strip()
            or "org.example.myapp"
        )
        version_name = self.get_argument("version_name", "1.0").strip() or "1.0"
        try:
            version_code = int(self.get_argument("version_code", "1"))
        except ValueError:
            version_code = 1
        email = self.get_argument("email", "").strip()

        # ── Validate fields ──────────────────────────────────────────────────
        import re

        if not re.match(r"^[a-zA-Z][a-zA-Z0-9 _\-]{0,49}$", app_name):
            self.write_error_json("Invalid app_name. Use letters, numbers, spaces, hyphens.", 400)
            return
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$", package_name):
            self.write_error_json(
                "Invalid package_name. Use lowercase reverse-domain notation "
                "(e.g. com.example.myapp).", 400
            )
            return

        # ── Save upload ──────────────────────────────────────────────────────
        Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
        safe_name = safe_filename(original_name)

        # Use a temporary path; final path will include the build_id
        tmp_path = os.path.join(config.UPLOAD_DIR, f"tmp_{os.urandom(8).hex()}_{safe_name}")
        with open(tmp_path, "wb") as f:
            f.write(body)

        # ── Security scan ────────────────────────────────────────────────────
        try:
            await tornado.ioloop.IOLoop.current().run_in_executor(
                None, validate_upload, tmp_path, original_name
            )
        except SecurityError as exc:
            os.remove(tmp_path)
            logger.warning("Rejected upload from %s: %s", self.request.remote_ip, exc)
            self.write_error_json(str(exc), 422)
            return
        except Exception as exc:
            os.remove(tmp_path)
            logger.error("Validation error: %s", exc)
            self.write_error_json("File validation failed.", 500)
            return

        # ── Handle optional icon ─────────────────────────────────────────────
        def _save_optional_image(field_name: str, prefix: str) -> str:
            files = self.request.files.get(field_name)
            if not files or not files[0]["body"]:
                return ""
            info = files[0]
            Path(config.ICON_DIR).mkdir(parents=True, exist_ok=True)
            ext = Path(info["filename"] or f"{prefix}.png").suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg"}:
                ext = ".png"
            path = os.path.join(config.ICON_DIR, f"{prefix}_{os.urandom(8).hex()}{ext}")
            with open(path, "wb") as f:
                f.write(info["body"])
            return path

        icon_path   = _save_optional_image("icon",   "icon")
        splash_path = _save_optional_image("splash", "splash")

        # ── Create build record ──────────────────────────────────────────────
        user_id = self.current_user.get("id") if self.current_user else None
        build_id = create_build(
            original_filename=original_name,
            app_name=app_name,
            package_name=package_name,
            version_name=version_name,
            version_code=version_code,
            upload_path=tmp_path,
            icon_path=icon_path,
            splash_path=splash_path,
            email_notification=email,
            user_id=user_id,
        )

        # Rename upload to include build_id for traceability
        final_path = os.path.join(config.UPLOAD_DIR, f"{build_id}_{safe_name}")
        os.rename(tmp_path, final_path)

        # Patch the upload_path in the DB now that we know build_id
        from app.database import get_db
        db = get_db()
        db.execute("UPDATE builds SET upload_path=? WHERE id=?", (final_path, build_id))
        db.commit()

        logger.info(
            "Upload accepted: build_id=%s file=%s size=%d",
            build_id, original_name, len(body),
        )

        self.write_json(
            {
                "build_id": build_id,
                "filename": original_name,
                "size": len(body),
                "app_name": app_name,
                "package_name": package_name,
                "version_name": version_name,
                "version_code": version_code,
                "status": "pending",
            },
            status=201,
        )
