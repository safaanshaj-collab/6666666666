"""
Security utilities: file validation, malicious content scanning,
magic-byte checking, and upload sanitisation.
"""

import hashlib
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Magic bytes for supported formats ────────────────────────────────────────
MAGIC_BYTES: dict[str, bytes] = {
    ".zip": b"PK\x03\x04",
    ".py":  b"",            # text – no magic bytes; check encoding instead
}

# Dangerous patterns to reject in Python source files
# NOTE: These are best-effort first-pass checks only.
# All code runs inside an isolated Docker container with no network access;
# Docker isolation is the primary security boundary.
DANGEROUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bos\.system\s*\(", re.I),
    re.compile(r"\bsubprocess\b", re.I),
    re.compile(r"\beval\s*\(", re.I),
    re.compile(r"\bexec\s*\(", re.I),
    re.compile(r"\b__import__\s*\(", re.I),
    re.compile(r"\bopen\s*\([^)]*['\"]w", re.I),
    re.compile(r"socket\s*\.", re.I),
    re.compile(r"requests\s*\.", re.I),
    re.compile(r"urllib\s*\.", re.I),
    re.compile(r"\brmtree\b", re.I),
    re.compile(r"\bshutil\b", re.I),
    re.compile(r"chmod\s*\(", re.I),
    re.compile(r"/etc/passwd", re.I),
    re.compile(r"\.\./", re.I),          # path traversal
]

# Max individual file size inside a zip (50 MB)
MAX_INNER_FILE_SIZE = 50 * 1024 * 1024
# Max number of files inside a zip
MAX_ZIP_FILES = 500
# Max uncompressed size (zip bomb guard, 500 MB)
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024


class SecurityError(ValueError):
    """Raised when an uploaded file fails a security check."""


def validate_extension(filename: str) -> str:
    """Return the lowercase extension or raise SecurityError."""
    ext = Path(filename).suffix.lower()
    if ext not in {".py", ".zip"}:
        raise SecurityError(
            f"File type '{ext}' is not allowed. Only .py and .zip files are accepted."
        )
    return ext


def check_magic_bytes(data: bytes, ext: str) -> None:
    """Verify the file starts with the expected magic bytes."""
    if ext == ".zip":
        if not data[:4] == MAGIC_BYTES[".zip"]:
            raise SecurityError("File claims to be a ZIP but has an invalid signature.")
    elif ext == ".py":
        try:
            data[:1024].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise SecurityError("Python file contains non-UTF-8 bytes; rejecting.")


def scan_python_source(source: str, filename: str = "<unknown>") -> list[str]:
    """
    Scan Python source code for obviously dangerous patterns.
    Returns a list of warning strings (does NOT raise – caller decides).
    Note: builds run inside an isolated Docker container with no network access,
    so this is a best-effort first-pass defence only, not the primary sandbox.
    """
    warnings: list[str] = []
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(source):
            warnings.append(f"Suspicious pattern '{pattern.pattern}' in {filename}")
    return warnings


def validate_zip(file_path: str) -> None:
    """
    Perform safety checks on a ZIP archive:
    - Valid ZIP structure
    - No path traversal entries
    - No zip-bomb (uncompressed ratio / total size)
    - File count limit
    - Scan .py files for dangerous patterns
    """
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            members = zf.infolist()
    except zipfile.BadZipFile:
        raise SecurityError("Uploaded file is not a valid ZIP archive.")

    if len(members) > MAX_ZIP_FILES:
        raise SecurityError(
            f"ZIP contains {len(members)} files; limit is {MAX_ZIP_FILES}."
        )

    total_uncompressed = 0
    py_count = 0

    for info in members:
        # Path traversal guard
        if ".." in info.filename or info.filename.startswith("/"):
            raise SecurityError(
                f"ZIP entry '{info.filename}' contains a path traversal sequence."
            )

        if info.file_size > MAX_INNER_FILE_SIZE:
            raise SecurityError(
                f"ZIP entry '{info.filename}' is larger than {MAX_INNER_FILE_SIZE // 1_000_000} MB."
            )

        total_uncompressed += info.file_size

        if total_uncompressed > MAX_UNCOMPRESSED_SIZE:
            raise SecurityError(
                "ZIP uncompressed content exceeds the allowed limit (zip bomb protection)."
            )

        if info.filename.endswith(".py"):
            py_count += 1

    if py_count == 0:
        raise SecurityError("ZIP archive contains no Python (.py) files.")

    # Scan .py files for dangerous patterns
    with zipfile.ZipFile(file_path, "r") as zf:
        for info in zf.infolist():
            if info.filename.endswith(".py") and info.file_size < MAX_INNER_FILE_SIZE:
                try:
                    source = zf.read(info.filename).decode("utf-8", errors="replace")
                    warnings = scan_python_source(source, info.filename)
                    for w in warnings:
                        logger.warning("Security scan: %s", w)
                except Exception as e:
                    logger.warning("Could not scan %s: %s", info.filename, e)


def validate_py(file_path: str) -> None:
    """Validate a standalone .py file."""
    with open(file_path, "rb") as f:
        raw = f.read()
    check_magic_bytes(raw, ".py")
    source = raw.decode("utf-8", errors="replace")
    warnings = scan_python_source(source, file_path)
    for w in warnings:
        logger.warning("Security scan: %s", w)


def validate_upload(file_path: str, original_filename: str) -> None:
    """Full validation pipeline for an uploaded file."""
    ext = validate_extension(original_filename)
    with open(file_path, "rb") as f:
        header = f.read(512)
    check_magic_bytes(header, ext)
    if ext == ".zip":
        validate_zip(file_path)
    elif ext == ".py":
        validate_py(file_path)
    logger.info("Upload validated: %s (%s)", original_filename, ext)


def safe_filename(filename: str) -> str:
    """Strip dangerous characters from a filename, keep extension."""
    name = Path(filename).stem
    ext = Path(filename).suffix.lower()
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)[:64]
    return f"{name}{ext}" if name else f"upload{ext}"


def file_sha256(path: str) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
