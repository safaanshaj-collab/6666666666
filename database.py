"""
SQLite database setup and connection management for Py2APK.
Uses WAL mode for better concurrency and thread-local connections.
"""

import logging
import sqlite3
import threading
from pathlib import Path

from app.config import config

logger = logging.getLogger(__name__)
_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating it if needed."""
    if getattr(_local, "conn", None) is None:
        Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA temp_store=MEMORY")
    return _local.conn


def close_db() -> None:
    """Close and discard the thread-local connection."""
    if getattr(_local, "conn", None) is not None:
        _local.conn.close()
        _local.conn = None


def init_db() -> None:
    """Create all tables and indexes if they don't already exist."""
    db = get_db()
    db.executescript(
        """
        -- ── Users ──────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            email         TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_admin      BOOLEAN  DEFAULT 0
        );

        -- ── Builds ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS builds (
            id                   TEXT    PRIMARY KEY,
            user_id              INTEGER REFERENCES users(id) ON DELETE SET NULL,
            original_filename    TEXT    NOT NULL,
            app_name             TEXT    NOT NULL DEFAULT 'MyApp',
            package_name         TEXT    NOT NULL DEFAULT 'org.example.myapp',
            version_name         TEXT    NOT NULL DEFAULT '1.0',
            version_code         INTEGER NOT NULL DEFAULT 1,
            status               TEXT    NOT NULL DEFAULT 'pending',
            -- status: pending | queued | building | success | failed | cancelled
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at           DATETIME,
            completed_at         DATETIME,
            duration_seconds     INTEGER,
            upload_path          TEXT,
            apk_path             TEXT,
            log_path             TEXT,
            icon_path            TEXT,
            splash_path          TEXT,
            error_message        TEXT,
            docker_container_id  TEXT,
            email_notification   TEXT,
            queue_position       INTEGER,
            expires_at           DATETIME DEFAULT (datetime('now', '+7 days'))
        );

        -- ── Build log lines ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS build_logs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            build_id  TEXT    NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
            ts        DATETIME DEFAULT CURRENT_TIMESTAMP,
            level     TEXT     DEFAULT 'INFO',
            message   TEXT     NOT NULL
        );

        -- ── Indexes ─────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_builds_status     ON builds(status);
        CREATE INDEX IF NOT EXISTS idx_builds_created_at ON builds(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_builds_user_id    ON builds(user_id);
        CREATE INDEX IF NOT EXISTS idx_builds_expires_at ON builds(expires_at);
        CREATE INDEX IF NOT EXISTS idx_logs_build_id     ON build_logs(build_id, id);
    """
    )
    db.commit()
    logger.info("Database initialised at %s", config.DB_PATH)
