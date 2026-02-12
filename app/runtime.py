from __future__ import annotations

from pathlib import Path
import os

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Transcript Processor"
RUNTIME_DIR = APP_SUPPORT_DIR / "runtime"
RUNTIME_PYTHON = RUNTIME_DIR / "python" / "bin" / "python3"
RUNTIME_VENV_PY = RUNTIME_DIR / "venv" / "bin" / "python"
INSTALL_MARKER = RUNTIME_DIR / ".installed"
RUNTIME_VERSION_MARKER = RUNTIME_DIR / ".runtime_version"
RUNTIME_VERSION = "0.1.4"


def runtime_exists() -> bool:
    if not (RUNTIME_VENV_PY.exists() and INSTALL_MARKER.exists() and RUNTIME_VERSION_MARKER.exists()):
        return False
    try:
        installed_version = RUNTIME_VERSION_MARKER.read_text(encoding="utf-8").strip()
    except Exception:
        return False
    return installed_version == RUNTIME_VERSION


def ensure_dirs() -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)


def runtime_url() -> str:
    # Override with environment variable in production
    return os.environ.get(
        "TPP_RUNTIME_URL",
        "https://github.com/tietjinator/twc-transcriptprocessor/releases/download/v0.1.0/runtime_payload.tar.gz",
    )
