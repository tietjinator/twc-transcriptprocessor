#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"

MANIFEST_OUT="${TPP_RUNTIME_MANIFEST_OUT:-$BUILD_DIR/runtime_manifest.json}"
PAYLOAD_PATH="${TPP_RUNTIME_PAYLOAD_PATH:-$BUILD_DIR/runtime_payload.tar.gz}"
PAYLOAD_URL="${TPP_RUNTIME_PAYLOAD_URL:-https://github.com/tietjinator/twc-transcriptprocessor/releases/download/v0.1.5/runtime_payload.tar.gz}"
PUBLISHED_AT="${TPP_RUNTIME_PUBLISHED_AT:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}"
RUNTIME_VERSION="${TPP_RUNTIME_VERSION:-}"

if [ -z "$RUNTIME_VERSION" ]; then
  RUNTIME_VERSION="$(python3 - <<'PY'
from pathlib import Path
import re

runtime_py = Path("app/runtime.py")
text = runtime_py.read_text(encoding="utf-8")
m = re.search(r'^RUNTIME_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
if not m:
    raise SystemExit("Could not find RUNTIME_VERSION in app/runtime.py")
print(m.group(1))
PY
)"
fi

if [ ! -f "$PAYLOAD_PATH" ]; then
  echo "Payload not found at $PAYLOAD_PATH"
  echo "Run scripts/build_runtime_payload.sh first."
  exit 1
fi

SHA256="$(shasum -a 256 "$PAYLOAD_PATH" | awk '{print $1}')"

mkdir -p "$(dirname "$MANIFEST_OUT")"
cat > "$MANIFEST_OUT" <<JSON
{
  "runtime_version": "$RUNTIME_VERSION",
  "payload_url": "$PAYLOAD_URL",
  "payload_sha256": "$SHA256",
  "published_at": "$PUBLISHED_AT"
}
JSON

echo "Manifest written to $MANIFEST_OUT"
