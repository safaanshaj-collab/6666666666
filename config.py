"""
Configuration management for Py2APK.
All settings can be overridden via environment variables.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Config:
    # ── Server ──────────────────────────────────────────────────────────────
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8080"))
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "change-this-secret-key-in-production-please!"
    )

    # ── Paths ────────────────────────────────────────────────────────────────
    DATA_DIR: Path = BASE_DIR / os.environ.get("DATA_DIR", "data")
    DB_PATH: str = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "py2apk.db"))
    UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
    BUILD_DIR: str = os.environ.get("BUILD_DIR", str(BASE_DIR / "data" / "builds"))
    APK_DIR: str = os.environ.get("APK_DIR", str(BASE_DIR / "data" / "apks"))
    ICON_DIR: str = os.environ.get("ICON_DIR", str(BASE_DIR / "data" / "icons"))

    # ── Upload limits ────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE: int = int(
        os.environ.get("MAX_UPLOAD_SIZE", str(100 * 1024 * 1024))
    )  # 100 MB
    ALLOWED_EXTENSIONS: set = {".py", ".zip"}

    # ── Docker build ─────────────────────────────────────────────────────────
    DOCKER_BUILDER_IMAGE: str = os.environ.get(
        "DOCKER_BUILDER_IMAGE", "py2apk-builder:latest"
    )
    DOCKER_MEMORY_LIMIT: str = os.environ.get("DOCKER_MEMORY_LIMIT", "4g")
    DOCKER_CPU_LIMIT: str = os.environ.get("DOCKER_CPU_LIMIT", "2")
    DOCKER_NETWORK: str = os.environ.get("DOCKER_NETWORK", "none")  # no network access
    BUILD_TIMEOUT: int = int(os.environ.get("BUILD_TIMEOUT", "3600"))  # 1 hour

    # ── Build queue ──────────────────────────────────────────────────────────
    MAX_CONCURRENT_BUILDS: int = int(os.environ.get("MAX_CONCURRENT_BUILDS", "2"))
    MAX_QUEUE_SIZE: int = int(os.environ.get("MAX_QUEUE_SIZE", "20"))

    # ── Authentication ───────────────────────────────────────────────────────
    ENABLE_AUTH: bool = os.environ.get("ENABLE_AUTH", "false").lower() == "true"
    SESSION_EXPIRY: int = int(os.environ.get("SESSION_EXPIRY", "86400"))  # 24 h

    # ── Cleanup ──────────────────────────────────────────────────────────────
    BUILD_EXPIRY_DAYS: int = int(os.environ.get("BUILD_EXPIRY_DAYS", "7"))
    CLEANUP_INTERVAL: int = int(os.environ.get("CLEANUP_INTERVAL", "3600"))  # 1 h

    # ── Email notification ───────────────────────────────────────────────────
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER: str = os.environ.get("SMTP_USER", "")
    SMTP_PASS: str = os.environ.get("SMTP_PASS", "")
    SMTP_FROM: str = os.environ.get("SMTP_FROM", "noreply@py2apk.local")

    # ── Pagination ───────────────────────────────────────────────────────────
    PAGE_SIZE: int = int(os.environ.get("PAGE_SIZE", "20"))


config = Config()
