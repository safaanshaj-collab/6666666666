# Py2APK

**Convert Python projects to Android APKs in the cloud.**

Py2APK is a self-hosted web application that takes your Python (Kivy/KivyMD) project, builds it inside an isolated Docker container with Android SDK, and hands you a ready-to-install APK — all through a modern web UI.

---

## Features

- **Drag-and-drop upload** — `.py` single file or `.zip` project archive
- **Real-time log streaming** — live build output via WebSocket
- **Docker-isolated builds** — each build runs in a fresh, network-isolated container
- **Custom app name, package, version, icon**
- **Build history** — search, filter, paginate, retry, delete
- **APK download** — chunked streaming download
- **Email notifications** — optional SMTP support
- **Dark / light theme**
- **REST API** — programmatic access to all operations
- **Auto-cleanup** — expired builds deleted automatically
- **Optional authentication** — single-user login gate

---

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose v2+
- 8 GB RAM (for the Android SDK / NDK build image)
- 20 GB free disk space

### 1 – Clone and configure

```bash
git clone https://github.com/yourname/py2apk.git
cd py2apk
cp .env.example .env
# Edit .env – at minimum change SECRET_KEY
```

### 2 – Build the Android SDK image (one-time, ~20-30 min)

```bash
docker build -f docker/Dockerfile.builder -t py2apk-builder:latest .
```

### 3 – Start the application

```bash
docker compose up -d web
```

Open **http://localhost:8080** in your browser.

### 4 – (Optional) Nginx reverse proxy with TLS

```bash
# Place your SSL certificate files in nginx/ssl/
# Edit nginx/nginx.conf to set your domain
docker compose --profile with-nginx up -d
```

---

## Running in Development

```bash
# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the server (auto-reloads with DEBUG=true)
DEBUG=true python3 -m app.main
```

---

## Project Structure

```
py2apk/
├── app/
│   ├── config.py           Configuration (env vars)
│   ├── database.py         SQLite setup
│   ├── main.py             Tornado app entry point
│   ├── handlers/           HTTP / WebSocket handlers
│   │   ├── base.py         Base handler (auth, helpers)
│   │   ├── auth.py         Login / logout / register
│   │   ├── upload.py       POST /api/upload
│   │   ├── build.py        Build start/cancel/retry/delete
│   │   ├── logs.py         WebSocket log streaming + download
│   │   ├── download.py     APK download
│   │   └── pages.py        HTML pages + list/stats API
│   ├── models/
│   │   └── build.py        Build + log CRUD helpers
│   └── utils/
│       ├── security.py     File validation & security scanning
│       ├── docker_builder.py Docker build runner + queue
│       └── cleanup.py      Periodic cleanup of expired builds
├── templates/              Tornado HTML templates
├── static/
│   ├── css/style.css       Main stylesheet (dark/light theme)
│   ├── css/upload.css      Upload page styles
│   ├── js/theme.js         Theme switcher
│   ├── js/main.js          Sidebar, flash messages
│   ├── js/upload.js        Drag-and-drop, XHR upload
│   └── js/build.js         WebSocket log streaming, status polling
├── docker/
│   ├── Dockerfile.builder  Android SDK + Buildozer image
│   └── entrypoint.sh       Build container entrypoint
├── nginx/
│   └── nginx.conf          Nginx reverse proxy config
├── Dockerfile              Main app container
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload` | Upload a `.py` or `.zip` file |
| `GET`  | `/api/builds` | List builds (paginated, filterable) |
| `GET`  | `/api/builds/{id}/status` | Get build status + metadata |
| `POST` | `/api/builds/{id}/start` | Start/queue a build |
| `POST` | `/api/builds/{id}/cancel` | Cancel a running build |
| `POST` | `/api/builds/{id}/retry` | Retry a failed build |
| `DELETE`| `/api/builds/{id}` | Delete build + all files |
| `GET`  | `/api/builds/{id}/download` | Download the APK |
| `GET`  | `/api/builds/{id}/logs` | Download full log as text |
| `GET`  | `/api/stats` | Build statistics |
| `WS`   | `/ws/builds/{id}/logs` | Stream live build logs |

### Upload example

```bash
curl -X POST http://localhost:8080/api/upload \
  -F "file=@myapp.zip" \
  -F "app_name=My App" \
  -F "package_name=com.example.myapp" \
  -F "version_name=1.0" \
  -F "version_code=1"
```

Response:
```json
{
  "build_id": "abc123...",
  "status": "pending",
  "app_name": "My App",
  "package_name": "com.example.myapp"
}
```

Then start the build:
```bash
curl -X POST http://localhost:8080/api/builds/abc123.../start
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required)* | Cookie signing key — change in production |
| `PORT` | `8080` | HTTP server port |
| `DEBUG` | `false` | Enable debug mode |
| `ENABLE_AUTH` | `false` | Require login to access the app |
| `DOCKER_BUILDER_IMAGE` | `py2apk-builder:latest` | Builder Docker image name |
| `DOCKER_MEMORY_LIMIT` | `4g` | RAM limit per build container |
| `DOCKER_CPU_LIMIT` | `2` | CPU limit per build container |
| `BUILD_TIMEOUT` | `3600` | Build timeout in seconds |
| `MAX_CONCURRENT_BUILDS` | `2` | Max simultaneous builds |
| `MAX_UPLOAD_SIZE` | `104857600` | Max upload size in bytes (100 MB) |
| `BUILD_EXPIRY_DAYS` | `7` | Days before a build is auto-deleted |
| `SMTP_HOST` | *(empty)* | SMTP server (leave blank to disable email) |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` / `SMTP_PASS` | *(empty)* | SMTP credentials |

---

## Security

- Uploaded files are **never executed on the host**.
- Every build runs in a **fresh Docker container** with:
  - No network access (`--network none`)
  - RAM and CPU limits
  - A hard timeout
  - A read-only source mount
- Files are scanned for obvious malicious patterns before build.
- ZIP archives are validated against path traversal, zip-bomb attacks, and file count limits.
- Build workspaces are deleted immediately after completion.
- Expired builds and their files are auto-cleaned on a schedule.

---

## Project Requirements

Your Python project must:

1. Use **[Kivy](https://kivy.org/)** or **KivyMD** as the UI framework.
2. Have a `main.py` at the project root.
3. (Optional) Include a `requirements.txt` listing additional dependencies.

**Example ZIP layout:**
```
myapp.zip/
├── main.py          ← Required
├── requirements.txt ← Optional
├── myapp.kv         ← Optional Kivy layout file
└── assets/
    └── logo.png
```

---

## Production Deployment

1. Set a strong `SECRET_KEY` in `.env`.
2. Enable authentication: `ENABLE_AUTH=true` and create an admin account via `/register` (while unprotected), then re-enable auth.
3. Configure Nginx with TLS (`nginx/nginx.conf`).
4. Set `BUILD_EXPIRY_DAYS` and `MAX_CONCURRENT_BUILDS` appropriate to your server resources.
5. Monitor disk usage in `data/apks/` — large builds accumulate quickly.

---

## License

MIT – see [LICENSE](LICENSE) file.
