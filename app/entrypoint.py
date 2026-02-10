from __future__ import annotations

import sys
import subprocess

try:
    from app.runtime import runtime_exists, RUNTIME_DIR, RUNTIME_VENV_PY
    from app.bootstrap import run_bootstrap_ui
except Exception:
    # Fallback for running as a script from the app/ directory
    from runtime import runtime_exists, RUNTIME_DIR, RUNTIME_VENV_PY  # type: ignore
    from bootstrap import run_bootstrap_ui  # type: ignore


def launch_real_app():
    app_entry = RUNTIME_DIR / "app" / "src" / "mac_app_modern.py"
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
