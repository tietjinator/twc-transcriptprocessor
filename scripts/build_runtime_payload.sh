#!/bin/bash
set -euo pipefail

# Build runtime payload for online bootstrap
# Placeholder: fill in once deps are finalized

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
RUNTIME_DIR="$BUILD_DIR/runtime"
PAYLOAD_OUT="$BUILD_DIR/runtime_payload.tar.gz"
REQS_PATH="${TPP_REQUIREMENTS:-/Users/matthewtietje/TranscriptProcessor/requirements.txt}"
APP_SRC_ROOT="${TPP_APP_SRC_ROOT:-/Users/matthewtietje/TranscriptProcessor}"
PYBS_URL="${TPP_PYBS_URL:-}"

mkdir -p "$BUILD_DIR"
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"

# 1) Download portable Python (python-build-standalone)
if [ -z "$PYBS_URL" ]; then
  PYBS_URL="$(python3 - <<'PY'
import json, urllib.request
url = 'https://api.github.com/repos/indygreg/python-build-standalone/releases/latest'
with urllib.request.urlopen(url) as r:
    data = json.load(r)
tag = data['tag_name']
assets = data['assets']
name = None
for a in assets:
    n = a['name']
    if 'cpython-3.12' in n and 'aarch64-apple-darwin' in n and 'install_only' in n and n.endswith('.tar.gz'):
        name = n
        break
if not name:
    raise SystemExit('No suitable python-build-standalone asset found')
print(f"https://github.com/indygreg/python-build-standalone/releases/download/{tag}/{name}")
PY
)"
fi

echo "Using Python runtime: $PYBS_URL"
PYBS_TAR="$BUILD_DIR/python-standalone.tar.gz"
curl -L "$PYBS_URL" -o "$PYBS_TAR"

# 2) Extract Python runtime into runtime/python
tar -xzf "$PYBS_TAR" -C "$RUNTIME_DIR"

# 3) Copy installer + requirements + app code
if [ -f "$REQS_PATH" ]; then
  cp "$REQS_PATH" "$RUNTIME_DIR/requirements.txt"
else
  echo "Requirements not found at $REQS_PATH. Skipping."
fi

cp "$PROJECT_ROOT/app/runtime_installer.py" "$RUNTIME_DIR/runtime_installer.py"
mkdir -p "$RUNTIME_DIR/app"

# Copy app source + assets from the main project
if [ -d "$APP_SRC_ROOT/src" ]; then
  mkdir -p "$RUNTIME_DIR/app/src"
  cp -R "$APP_SRC_ROOT/src/." "$RUNTIME_DIR/app/src/"
else
  echo "App src not found at $APP_SRC_ROOT/src"
fi

if [ -d "$APP_SRC_ROOT/assets" ]; then
  mkdir -p "$RUNTIME_DIR/app/assets"
  cp -R "$APP_SRC_ROOT/assets/." "$RUNTIME_DIR/app/assets/"
fi

if [ -f "$APP_SRC_ROOT/scripts/save_api_key.py" ]; then
  mkdir -p "$RUNTIME_DIR/app/scripts"
  cp "$APP_SRC_ROOT/scripts/save_api_key.py" "$RUNTIME_DIR/app/scripts/"
fi

if [ ! -f "$RUNTIME_DIR/app/src/mac_app_modern.py" ]; then
  echo "Expected app entry not found in payload. Check APP_SRC_ROOT."
  exit 1
fi

# 4) Add ffmpeg / native libs (placeholder)
# cp /path/to/ffmpeg "$RUNTIME_DIR/"

# 5) Package runtime payload
cd "$RUNTIME_DIR"
tar -czf "$PAYLOAD_OUT" .

echo "Payload written to $PAYLOAD_OUT"
