# ============================================================
# Py2APK – Main application container
# Runs the Tornado web server.
# ============================================================

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Create non-root user ──────────────────────────────────────────────────────
RUN groupadd -g 1000 py2apk && \
    useradd -u 1000 -g py2apk -m -s /bin/bash py2apk && \
    # Allow the app to run docker commands (must be in docker group)
    usermod -aG docker py2apk

# ── Application ───────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directories
RUN mkdir -p data/uploads data/builds data/apks data/icons && \
    chown -R py2apk:py2apk /app

USER py2apk

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8080

ENV HOST=0.0.0.0
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

CMD ["python3", "-m", "app.main"]
