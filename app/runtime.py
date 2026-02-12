from __future__ import annotations

from pathlib import Path
import os
import re

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Transcript Processor"
RUNTIME_DIR = APP_SUPPORT_DIR / "runtime"
MODEL_CACHE_DIR = APP_SUPPORT_DIR / "models" / "huggingface"
RUNTIME_PYTHON = RUNTIME_DIR / "python" / "bin" / "python3"
RUNTIME_VENV_PY = RUNTIME_DIR / "venv" / "bin" / "python"
INSTALL_MARKER = RUNTIME_DIR / ".installed"
RUNTIME_VERSION_MARKER = RUNTIME_DIR / ".runtime_version"
RUNTIME_VERSION = "0.1.9"
RUNTIME_MANIFEST_URL = "https://github.com/tietjinator/twc-transcriptprocessor/releases/download/v0.1.5/runtime_manifest.json"


def runtime_installed() -> bool:
    if not (RUNTIME_VENV_PY.exists() and INSTALL_MARKER.exists() and RUNTIME_VERSION_MARKER.exists()):
        return False
    return True


def installed_runtime_version() -> str | None:
    try:
        return RUNTIME_VERSION_MARKER.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def runtime_exists() -> bool:
    if not runtime_installed():
        return False
    installed_version = installed_runtime_version()
    if not installed_version:
        return False
    return installed_version == RUNTIME_VERSION


def ensure_dirs() -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)


def runtime_url() -> str:
    # Override with environment variable in production
    return os.environ.get(
        "TPP_RUNTIME_URL",
        "https://github.com/tietjinator/twc-transcriptprocessor/releases/download/v0.1.5/runtime_payload.tar.gz",
    )


def runtime_manifest_url() -> str:
    return os.environ.get("TPP_RUNTIME_MANIFEST_URL", RUNTIME_MANIFEST_URL)


def parse_version(version: str) -> tuple[int, ...]:
    if not version or not re.fullmatch(r"\d+(?:\.\d+)*", version):
        raise ValueError(f"Invalid version string: {version!r}")
    return tuple(int(part) for part in version.split("."))


def is_remote_newer(local_version: str, remote_version: str) -> bool:
    local = parse_version(local_version)
    remote = parse_version(remote_version)
    length = max(len(local), len(remote))
    local_norm = local + (0,) * (length - len(local))
    remote_norm = remote + (0,) * (length - len(remote))
    return remote_norm > local_norm
