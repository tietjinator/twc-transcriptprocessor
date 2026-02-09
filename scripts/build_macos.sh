#!/bin/bash
set -euo pipefail

# Build script for macOS bootstrap app (PyInstaller)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
VENV_DIR="$BUILD_DIR/venv-build"

echo "Project: $PROJECT_ROOT"
echo "Build dir: $BUILD_DIR"

mkdir -p "$BUILD_DIR"

# 1) Create isolated build venv
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

# 2) Install build dependencies
"$VENV_DIR/bin/pip" install pyinstaller

# 3) Build app with PyInstaller (spec file)
"$VENV_DIR/bin/pyinstaller" \
  --clean \
  --noconfirm \
  --distpath "$BUILD_DIR/dist" \
  --workpath "$BUILD_DIR/pyinstaller" \
  "$PROJECT_ROOT/scripts/pyinstaller.spec"

echo "Build complete."
