#!/bin/bash
set -euo pipefail

# Build script for macOS bootstrap app (PyInstaller)

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
VENV_DIR="$BUILD_DIR/venv-build"
BUILD_PYTHON="${TPP_BUILD_PYTHON:-}"
RUNTIME_PYTHON="$BUILD_DIR/runtime/python/bin/python3.12"
VENV_PY_MARKER="$VENV_DIR/.build_python"
APP_NAME="Transcript Processor.app"
DMG_NAME="Transcript_Processor.dmg"
DMG_VOLUME_NAME="Transcript Processor"

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
  EXPECTED_VENV_PY="$VENV_DIR/bin/python$PY_VER"

  # Repair stale/broken venvs after runtime Python refreshes.
  if [ ! -x "$VENV_DIR/bin/python" ] || [ ! -x "$EXPECTED_VENV_PY" ]; then
    RECREATE_VENV=1
  fi

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

APP_PATH="$BUILD_DIR/dist/$APP_NAME"
if [ ! -d "$APP_PATH" ]; then
  echo "App bundle not found at $APP_PATH"
  exit 1
fi

DMG_STAGING="$BUILD_DIR/dmg"
DMG_BACKGROUND_DIR="$DMG_STAGING/.background"
DMG_BACKGROUND="$DMG_BACKGROUND_DIR/background.png"
TMP_DMG="$BUILD_DIR/Transcript_Processor_tmp.dmg"
FINAL_DMG="$BUILD_DIR/$DMG_NAME"

mkdir -p "$DMG_BACKGROUND_DIR"
rm -rf "$DMG_STAGING/$APP_NAME"
rm -rf "$DMG_STAGING/Applications"
cp -R "$APP_PATH" "$DMG_STAGING/$APP_NAME"
ln -sfn /Applications "$DMG_STAGING/Applications"

/usr/bin/swift "$PROJECT_ROOT/scripts/generate_dmg_background.swift" "$DMG_BACKGROUND"

rm -f "$TMP_DMG" "$FINAL_DMG"
hdiutil create -volname "$DMG_VOLUME_NAME" -srcfolder "$DMG_STAGING" -ov -format UDRW "$TMP_DMG" >/dev/null

ATTACH_OUTPUT="$(hdiutil attach -readwrite -noverify -noautoopen "$TMP_DMG")"
MOUNT_POINT="$(echo "$ATTACH_OUTPUT" | awk -F '\t' '/\/Volumes\// {print $NF; exit}')"
if [ -z "$MOUNT_POINT" ]; then
  echo "Failed to mount temporary DMG."
  exit 1
fi

osascript <<APPLESCRIPT
tell application "Finder"
  tell disk "$DMG_VOLUME_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {120, 120, 800, 540}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 128
    set text size of viewOptions to 14
    set background picture of viewOptions to file ".background:background.png"
    set position of item "Transcript Processor.app" of container window to {170, 220}
    set position of item "Applications" of container window to {510, 220}
    close
    open
    update without registering applications
    delay 1
  end tell
end tell
APPLESCRIPT

hdiutil detach "$MOUNT_POINT" -quiet
hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -ov -o "$FINAL_DMG" >/dev/null
rm -f "$TMP_DMG"

echo "Build complete."
echo "App: $APP_PATH"
echo "DMG: $FINAL_DMG"
