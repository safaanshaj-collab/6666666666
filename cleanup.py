"""
Automatic cleanup of expired builds and orphaned files.
Runs periodically as a Tornado PeriodicCallback.
"""

import logging
import os
import shutil
from pathlib import Path

from app.config import config
from app.models.build import get_expired_builds, delete_build

logger = logging.getLogger(__name__)


def _remove_path(path: str) -> None:
    """Remove a file or directory, ignoring errors."""
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning("Cleanup: could not remove %s – %s", path, e)


def cleanup_expired_builds() -> int:
    """
    Delete all builds whose expires_at has passed.
    Returns the number of builds removed.
    """
    expired = get_expired_builds()
    removed = 0

    for build in expired:
        build_id = build["id"]
        logger.info("Cleaning up expired build %s", build_id)

        # Remove associated files
        for path_key in ("upload_path", "apk_path", "icon_path", "splash_path"):
            if build.get(path_key):
                _remove_path(build[path_key])

        # Remove APK output directory
        apk_dir = os.path.join(config.APK_DIR, build_id)
        _remove_path(apk_dir)

        # Remove build workspace if it somehow persists
        build_workspace = os.path.join(config.BUILD_DIR, build_id)
        _remove_path(build_workspace)

        # Remove from database (cascade deletes logs)
        try:
            delete_build(build_id)
            removed += 1
        except Exception as e:
            logger.error("Failed to delete build record %s: %s", build_id, e)

    if removed:
        logger.info("Cleanup: removed %d expired build(s)", removed)

    return removed


def cleanup_orphaned_files() -> None:
    """
    Remove files in upload/apk/build directories that have no matching
    database record (e.g. left by a crash during upload).
    """
    from app.database import get_db

    db = get_db()
    known_ids: set[str] = {
        row[0] for row in db.execute("SELECT id FROM builds").fetchall()
    }

    for base_dir in (config.APK_DIR, config.BUILD_DIR):
        if not os.path.isdir(base_dir):
            continue
        for entry in os.scandir(base_dir):
            if entry.is_dir() and entry.name not in known_ids:
                logger.info("Cleanup: removing orphaned directory %s", entry.path)
                shutil.rmtree(entry.path, ignore_errors=True)


def run_cleanup() -> None:
    """Entry point called by the periodic scheduler."""
    try:
        n = cleanup_expired_builds()
        cleanup_orphaned_files()
        logger.debug("Periodic cleanup finished (removed %d)", n)
    except Exception:
        logger.exception("Error during periodic cleanup")
