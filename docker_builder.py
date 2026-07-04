"""
Docker build runner.

Each APK build runs inside a fresh, isolated Docker container with:
- No network access  (--network none)
- CPU and RAM limits
- A hard timeout
- Read-only source mount; writable output mount

Build output is streamed line-by-line via an async generator and is also
written to the database log table in real time.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import AsyncGenerator, Optional

from app.config import config
from app.models.build import append_log, set_apk_path, update_build_status

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _prepare_source_dir(upload_path: str, build_workspace: str) -> str:
    """
    Extract ZIP or copy .py into build_workspace/src/.
    Returns the path of the directory that will be mounted into Docker.
    """
    src_dir = Path(build_workspace) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    if upload_path.endswith(".zip"):
        with zipfile.ZipFile(upload_path, "r") as zf:
            zf.extractall(src_dir)
        # If everything was nested inside a single top-level folder, descend
        entries = list(src_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return str(entries[0])
    else:
        # Single .py file → create a minimal buildozer project
        dest = src_dir / Path(upload_path).name
        shutil.copy2(upload_path, dest)

    return str(src_dir)


def _find_apk(output_dir: str) -> Optional[str]:
    """Return the path of the first .apk found in output_dir."""
    for root, _, files in os.walk(output_dir):
        for fname in files:
            if fname.endswith(".apk"):
                return os.path.join(root, fname)
    return None


def _build_docker_command(
    build_id: str,
    src_dir: str,
    out_dir: str,
    icon_path: Optional[str],
    splash_path: Optional[str],
    app_name: str,
    package_name: str,
    version_name: str,
    version_code: int,
) -> list[str]:
    """Construct the `docker run` command.

    We do NOT use --read-only because the entrypoint script needs to write to
    /workspace/.buildozer_workspace (a temp copy of sources) and buildozer
    itself writes many intermediate files throughout /workspace/.buildozer.
    Security is still enforced via:
      - --network none  (no network access)
      - --security-opt no-new-privileges
      - CPU / RAM limits
      - Hard timeout enforced by asyncio.timeout()
      - Read-only source mount  (:ro)
    """
    cmd = [
        "docker", "run",
        "--rm",
        # Store the name so we can kill it on cancel
        "--name", f"py2apk-{build_id[:12]}",
        "--network", config.DOCKER_NETWORK,
        "--memory", config.DOCKER_MEMORY_LIMIT,
        "--cpus",   config.DOCKER_CPU_LIMIT,
        "--security-opt", "no-new-privileges",
        # Source (read-only) and APK output (writable)
        "-v", f"{src_dir}:/workspace/src:ro",
        "-v", f"{out_dir}:/workspace/output:rw",
        # Writable tmpfs for buildozer cache (exec needed for compiled artefacts)
        "--tmpfs", "/workspace/.buildozer:exec,size=3g",
        # Writable tmpfs for the entrypoint's working copy of source
        "--tmpfs", "/workspace/.buildozer_workspace:exec,size=2g",
    ]

    if icon_path and os.path.isfile(icon_path):
        cmd += ["-v", f"{icon_path}:/workspace/icon.png:ro"]

    if splash_path and os.path.isfile(splash_path):
        cmd += ["-v", f"{splash_path}:/workspace/splash.png:ro"]

    cmd += [
        config.DOCKER_BUILDER_IMAGE,
        "--app-name",      app_name,
        "--package-name",  package_name,
        "--version-name",  version_name,
        "--version-code",  str(version_code),
    ]
    return cmd


# ── Main build coroutine ─────────────────────────────────────────────────────

async def run_build(
    build_id: str,
    upload_path: str,
    app_name: str,
    package_name: str,
    version_name: str,
    version_code: int,
    icon_path: Optional[str] = None,
    splash_path: Optional[str] = None,
    email: Optional[str] = None,
) -> None:
    """
    Full build pipeline. Updates the database as each stage completes.
    Intended to be run as a background asyncio task.
    """
    build_workspace = os.path.join(config.BUILD_DIR, build_id)
    out_dir = os.path.join(config.APK_DIR, build_id)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    def log(msg: str, level: str = "INFO") -> None:
        logger.log(logging.getLevelName(level), "[%s] %s", build_id[:8], msg)
        append_log(build_id, msg, level)

    try:
        update_build_status(build_id, "building")
        log("▶ Build started")

        # ── Prepare source ───────────────────────────────────────────────────
        log("📦 Preparing source directory…")
        src_dir = await asyncio.to_thread(
            _prepare_source_dir, upload_path, build_workspace
        )
        log(f"   Source: {src_dir}")

        # ── Run Docker container ─────────────────────────────────────────────
        cmd = _build_docker_command(
            build_id, src_dir, out_dir, icon_path, splash_path,
            app_name, package_name, version_name, version_code,
        )
        log("🐳 Launching build container…")
        log(f"   Image: {config.DOCKER_BUILDER_IMAGE}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # Persist the container name so BuildCancelHandler can kill it
        container_name = f"py2apk-{build_id[:12]}"
        update_build_status(build_id, "building", docker_container_id=container_name)

        # ── Stream logs ──────────────────────────────────────────────────────
        start_time = time.monotonic()
        assert process.stdout is not None

        try:
            async with asyncio.timeout(config.BUILD_TIMEOUT):
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    # Detect log level from buildozer output
                    level = "INFO"
                    if "[ERROR]" in decoded or "ERROR" in decoded:
                        level = "ERROR"
                    elif "[WARNING]" in decoded or "WARNING" in decoded:
                        level = "WARNING"
                    elif "# Command failed" in decoded:
                        level = "ERROR"
                    log(decoded, level)
        except TimeoutError:
            process.kill()
            await process.wait()
            update_build_status(
                build_id, "failed",
                error_message=f"Build exceeded the {config.BUILD_TIMEOUT}s timeout."
            )
            log("⏱ Build timed out", "ERROR")
            return

        await process.wait()
        elapsed = round(time.monotonic() - start_time)

        # ── Check result ─────────────────────────────────────────────────────
        if process.returncode == 0:
            apk = _find_apk(out_dir)
            if apk:
                set_apk_path(build_id, apk)
                update_build_status(
                    build_id, "success",
                    duration_seconds=elapsed,
                )
                log(f"✅ Build succeeded in {elapsed}s  →  {os.path.basename(apk)}")
                if email:
                    await _send_notification(email, build_id, "success", app_name)
            else:
                update_build_status(
                    build_id, "failed",
                    error_message="Docker exited 0 but no APK was produced.",
                    duration_seconds=elapsed,
                )
                log("❌ No APK found in output directory", "ERROR")
        else:
            update_build_status(
                build_id, "failed",
                error_message=f"Docker exited with code {process.returncode}.",
                duration_seconds=elapsed,
            )
            log(f"❌ Build failed (exit {process.returncode})", "ERROR")
            if email:
                await _send_notification(email, build_id, "failed", app_name)

    except Exception as exc:
        logger.exception("Unexpected error for build %s", build_id)
        update_build_status(build_id, "failed", error_message=str(exc))
        append_log(build_id, f"Unexpected error: {exc}", "ERROR")
    finally:
        # Clean up the temporary build workspace (source copy + buildozer cache)
        if os.path.isdir(build_workspace):
            shutil.rmtree(build_workspace, ignore_errors=True)
            log("🧹 Build workspace cleaned up")


# ── Email notification ────────────────────────────────────────────────────────

async def _send_notification(
    email: str, build_id: str, status: str, app_name: str
) -> None:
    """Send an email notification (best-effort, errors are logged not raised)."""
    from app.config import config as cfg
    if not cfg.SMTP_HOST:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText

        subject = f"Py2APK: {app_name} build {status}"
        body = (
            f"Your build for '{app_name}' has completed with status: {status}.\n\n"
            f"Build ID: {build_id}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg.SMTP_FROM
        msg["To"] = email

        def _send():
            with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT) as s:
                s.starttls()
                if cfg.SMTP_USER:
                    s.login(cfg.SMTP_USER, cfg.SMTP_PASS)
                s.send_message(msg)

        await asyncio.to_thread(_send)
        logger.info("Notification sent to %s for build %s", email, build_id)
    except Exception as e:
        logger.warning("Failed to send email notification: %s", e)


# ── Build queue ───────────────────────────────────────────────────────────────

class BuildQueue:
    """Simple asyncio semaphore-based concurrency limiter."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._active: set[str] = set()

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def submit(self, build_id: str, **kwargs) -> None:
        """Enqueue and execute a build, respecting the concurrency limit."""
        from app.models.build import update_build_status
        update_build_status(build_id, "queued")
        async with self._sem:
            self._active.add(build_id)
            try:
                await run_build(build_id, **kwargs)
            finally:
                self._active.discard(build_id)


# Singleton queue used by the application
build_queue = BuildQueue(max_concurrent=config.MAX_CONCURRENT_BUILDS)
