#!/usr/bin/env python3
"""
Py2APK – development / production startup script.

Usage:
    python3 run.py                  # uses .env if present
    PORT=9000 python3 run.py        # override port
    DEBUG=true python3 run.py       # enable debug / auto-reload
"""

import asyncio
import os
import sys
from pathlib import Path

# ── Load .env if present ──────────────────────────────────────────────────────
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ── Start the Tornado server ──────────────────────────────────────────────────
from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down…")
        sys.exit(0)
