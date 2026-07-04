#!/usr/bin/env bash
# ============================================================
# Py2APK Builder – container entrypoint
#
# Arguments:
#   --app-name     <string>   App display name
#   --package-name <string>   Android package (e.g. com.example.myapp)
#   --version-name <string>   Semantic version (e.g. 1.0.0)
#   --version-code <int>      Integer version code
# ============================================================
set -euo pipefail

APP_NAME="MyApp"
PACKAGE_NAME="org.example.myapp"
VERSION_NAME="1.0"
VERSION_CODE="1"

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-name)      APP_NAME="$2";      shift 2 ;;
    --package-name)  PACKAGE_NAME="$2";  shift 2 ;;
    --version-name)  VERSION_NAME="$2";  shift 2 ;;
    --version-code)  VERSION_CODE="$2";  shift 2 ;;
    *) echo "[WARNING] Unknown argument: $1"; shift ;;
  esac
done

echo "==================================================="
echo "  Py2APK Builder"
echo "  App:     $APP_NAME"
echo "  Package: $PACKAGE_NAME"
echo "  Version: $VERSION_NAME ($VERSION_CODE)"
echo "==================================================="

# ── Prepare build directory ──────────────────────────────────────────────────
BUILD_DIR="/workspace/.buildozer_workspace"
mkdir -p "$BUILD_DIR"

# Copy sources (src mount is read-only)
echo "[INFO] Copying sources…"
cp -r /workspace/src/. "$BUILD_DIR/"

# ── Copy icon if provided ────────────────────────────────────────────────────
if [[ -f /workspace/icon.png ]]; then
  echo "[INFO] Using custom icon."
  cp /workspace/icon.png "$BUILD_DIR/icon.png"
fi

cd "$BUILD_DIR"

# ── Ensure main.py exists ─────────────────────────────────────────────────────
if [[ ! -f main.py ]]; then
  # Try to find a .py file to use as main
  PY_FILE=$(find . -maxdepth 2 -name "*.py" | head -1)
  if [[ -n "$PY_FILE" ]]; then
    echo "[WARNING] No main.py found. Using $PY_FILE as entry point."
    cp "$PY_FILE" main.py
  else
    echo "[ERROR] No Python file found in the project."
    exit 1
  fi
fi

# ── Generate buildozer.spec ───────────────────────────────────────────────────
echo "[INFO] Generating buildozer.spec…"

ICON_LINE=""
if [[ -f icon.png ]]; then
  ICON_LINE="icon.filename = icon.png"
fi

SPLASH_LINE=""
if [[ -f /workspace/splash.png ]]; then
  cp /workspace/splash.png "$BUILD_DIR/splash.png"
  SPLASH_LINE="presplash.filename = splash.png"
fi

# Read requirements from requirements.txt if present
REQUIREMENTS="kivy,python3"
if [[ -f requirements.txt ]]; then
  # Flatten requirements.txt into a comma-separated list, skip comments/empty
  EXTRA=$(grep -v '^\s*#' requirements.txt | grep -v '^\s*$' | tr '\n' ',' | sed 's/,$//')
  if [[ -n "$EXTRA" ]]; then
    REQUIREMENTS="kivy,python3,$EXTRA"
  fi
fi

cat > buildozer.spec <<EOF
[app]
title = $APP_NAME
package.name = $(echo "$PACKAGE_NAME" | awk -F. '{print $NF}')
package.domain = $(echo "$PACKAGE_NAME" | awk -F. 'NF>1{OFS=".";$NF="";print substr($0,1,length($0)-1)}')
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt
version = $VERSION_NAME
requirements = $REQUIREMENTS
${ICON_LINE}
${SPLASH_LINE}
orientation = portrait
osx.python_version = 3
osx.kivy_version = 1.9.1

[buildozer]
log_level = 2
warn_on_root = 1
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33
android.build_tools_version = 33.0.2
android.accept_sdk_license = True
android.arch = arm64-v8a
EOF

echo "[INFO] buildozer.spec written."
cat buildozer.spec

# ── Link the shared SDK / NDK into .buildozer to avoid re-download ────────────
mkdir -p .buildozer/android/platform
if [[ -d "$ANDROID_HOME" ]]; then
  ln -sfn "$ANDROID_HOME"          .buildozer/android/platform/android-sdk    2>/dev/null || true
  ln -sfn "$ANDROID_NDK_HOME"      .buildozer/android/platform/android-ndk    2>/dev/null || true
fi

# ── Run Buildozer ─────────────────────────────────────────────────────────────
echo "[INFO] Starting buildozer android debug…"
buildozer -v android debug 2>&1

# ── Copy APK to output ────────────────────────────────────────────────────────
APK_PATH=$(find .buildozer/android/platform/build-arm64-v8a/dists -name "*.apk" 2>/dev/null | head -1 || true)
if [[ -z "$APK_PATH" ]]; then
  APK_PATH=$(find . -name "*.apk" 2>/dev/null | head -1 || true)
fi

if [[ -n "$APK_PATH" ]]; then
  SAFE_NAME=$(echo "${APP_NAME}" | tr ' ' '_' | tr -dc '[:alnum:]_-')
  DEST="/workspace/output/${SAFE_NAME}-${VERSION_NAME}-debug.apk"
  cp "$APK_PATH" "$DEST"
  echo "[SUCCESS] APK saved: $DEST"
else
  echo "[ERROR] No APK found after build. Check the logs above."
  exit 1
fi
