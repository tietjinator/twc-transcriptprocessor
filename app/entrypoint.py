from __future__ import annotations

import sys
import subprocess

from .runtime import runtime_exists, RUNTIME_DIR, RUNTIME_VENV_PY
from .bootstrap import run_bootstrap_ui


def launch_real_app():
    app_entry = RUNTIME_DIR / "app" / "real_app.py"
    if not RUNTIME_VENV_PY.exists():
        print("Runtime python not found. Please run setup again.")
        return 1
    if not app_entry.exists():
        print("Runtime app entry not found. Please reinstall runtime.")
        return 1

    subprocess.Popen([str(RUNTIME_VENV_PY), str(app_entry)])
    return 0


def main():
    if runtime_exists():
        launch_real_app()
        return 0

    run_bootstrap_ui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
