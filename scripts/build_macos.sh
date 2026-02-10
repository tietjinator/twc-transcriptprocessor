#!/bin/bash
set -euo pipefail

# Build script for macOS bootstrap app (PyInstaller)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
VENV_DIR="$BUILD_DIR/venv-build"
BUILD_PYTHON="${TPP_BUILD_PYTHON:-}"
RUNTIME_PYTHON="$BUILD_DIR/runtime/python/bin/python3.12"
VENV_PY_MARKER="$VENV_DIR/.build_python"

echo "Project: $PROJECT_ROOT"
echo "Build dir: $BUILD_DIR"

mkdir -p "$BUILD_DIR"

# 1) Resolve build Python.
if [ -z "$BUILD_PYTHON" ] && [ -x "$RUNTIME_PYTHON" ]; then
  BUILD_PYTHON="$RUNTIME_PYTHON"
fi

if [ -z "$BUILD_PYTHON" ]; then
  BUILD_PYTHON="$(command -v python3 || true)"
fi

if [ -z "$BUILD_PYTHON" ] || [ ! -x "$BUILD_PYTHON" ]; then
  echo "No usable python3 found for build."
  echo "Run scripts/build_runtime_payload.sh first, or set TPP_BUILD_PYTHON."
  exit 1
fi

PY_INFO="$("$BUILD_PYTHON" -c 'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.python_implementation()}|{sys.executable}")')"
PY_VER="${PY_INFO%%|*}"
PY_REST="${PY_INFO#*|}"
PY_IMPL="${PY_REST%%|*}"

if [ "$BUILD_PYTHON" = "/usr/bin/python3" ] && [ "$PY_VER" = "3.9" ]; then
  echo "Refusing to build with Apple system Python 3.9 (Tk 8.5 causes runtime crash)."
  echo "Run scripts/build_runtime_payload.sh first so build/runtime/python is available."
  echo "Or set TPP_BUILD_PYTHON to a non-system Python with Tk support."
  exit 1
fi

echo "Using build Python: $BUILD_PYTHON ($PY_IMPL $PY_VER)"

# 2) Create isolated build venv (recreate if interpreter changed or unknown).
if [ -d "$VENV_DIR" ]; then
  RECREATE_VENV=0
  if [ ! -f "$VENV_PY_MARKER" ]; then
    RECREATE_VENV=1
  else
    PREV_PY="$(cat "$VENV_PY_MARKER" || true)"
    if [ "$PREV_PY" != "$BUILD_PYTHON" ]; then
      RECREATE_VENV=1
    fi
  fi

  if [ "$RECREATE_VENV" -eq 1 ]; then
    mv "$VENV_DIR" "$VENV_DIR.bak.$(date +%s)"
  fi
fi

if [ ! -d "$VENV_DIR" ]; then
  "$BUILD_PYTHON" -m venv "$VENV_DIR"
  echo "$BUILD_PYTHON" > "$VENV_PY_MARKER"
fi

"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel

# 3) Install build dependencies
"$VENV_DIR/bin/pip" install pyinstaller

# 4) Build app with PyInstaller (spec file)
"$VENV_DIR/bin/pyinstaller" \
  --clean \
  --noconfirm \
  --distpath "$BUILD_DIR/dist" \
  --workpath "$BUILD_DIR/pyinstaller" \
  "$PROJECT_ROOT/scripts/pyinstaller.spec"

echo "Build complete."
