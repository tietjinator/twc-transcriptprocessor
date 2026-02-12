from __future__ import annotations

import sys
import subprocess
import os

try:
    from app.runtime import runtime_installed, RUNTIME_DIR, RUNTIME_VENV_PY
    from app.bootstrap import run_bootstrap_ui
    from app.updater import run_startup_update_flow, STARTUP_UPDATE_LOG
except Exception:
    # Fallback for running as a script from the app/ directory
    from runtime import runtime_installed, RUNTIME_DIR, RUNTIME_VENV_PY  # type: ignore
    from bootstrap import run_bootstrap_ui  # type: ignore
    from updater import run_startup_update_flow, STARTUP_UPDATE_LOG  # type: ignore


def launch_real_app():
    app_entry = RUNTIME_DIR / "app" / "src" / "mac_app_modern.py"
    if not RUNTIME_VENV_PY.exists():
        print("Runtime python not found. Please run setup again.")
        return 1
    if not app_entry.exists():
        print("Runtime app entry not found. Please reinstall runtime.")
        return 1

    env = os.environ.copy()
    app_src = str(RUNTIME_DIR / "app" / "src")
    env["PYTHONPATH"] = app_src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")

    tcl_dir = RUNTIME_DIR / "python" / "lib" / "tcl9.0"
    tk_dir = RUNTIME_DIR / "python" / "lib" / "tk9.0"
    if tcl_dir.exists():
        env["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir.exists():
        env["TK_LIBRARY"] = str(tk_dir)
    fallback_libs = ["/opt/homebrew/lib", "/usr/local/lib"]
    existing = env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(fallback_libs + ([existing] if existing else []))

    subprocess.Popen([str(RUNTIME_VENV_PY), str(app_entry)], cwd=str(RUNTIME_DIR / "app"), env=env)
    return 0


def _show_launch_blocked(message: str):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Transcript Processor - Launch Blocked",
            message + f"\n\nUpdate log:\n{STARTUP_UPDATE_LOG}",
        )
        root.destroy()
    except Exception:
        print("Launch blocked:", message)
        print("Update log:", STARTUP_UPDATE_LOG)


def main():
    if not runtime_installed():
        run_bootstrap_ui()
        return 0

    decision = run_startup_update_flow()
    if decision.action in ("launch_current", "updated_and_launch"):
        rc = launch_real_app()
        if rc != 0:
            run_bootstrap_ui()
        return 0
    if decision.action == "bootstrap_required":
        run_bootstrap_ui()
        return 0
    if decision.action == "launch_blocked":
        _show_launch_blocked(decision.error or "Runtime update integrity check failed.")
        return 1

    launch_real_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
