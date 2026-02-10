from __future__ import annotations

from pathlib import Path
import os

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Transcript Processor"
RUNTIME_DIR = APP_SUPPORT_DIR / "runtime"
RUNTIME_PYTHON = RUNTIME_DIR / "python" / "bin" / "python3"
RUNTIME_VENV_PY = RUNTIME_DIR / "venv" / "bin" / "python"
INSTALL_MARKER = RUNTIME_DIR / ".installed"


def runtime_exists() -> bool:
    return RUNTIME_VENV_PY.exists() and INSTALL_MARKER.exists()


def ensure_dirs() -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)


def runtime_url() -> str:
    # Override with environment variable in production
    return os.environ.get(
        "TPP_RUNTIME_URL",
        "https://github.com/tietjinator/twc-transcriptprocessor/releases/download/v0.1.0/runtime_payload.tar.gz",
    )
