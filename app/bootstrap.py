from __future__ import annotations

import os
import queue
import threading
import urllib.request
import tarfile
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from .runtime import APP_SUPPORT_DIR, RUNTIME_DIR, RUNTIME_PYTHON, runtime_url, ensure_dirs

RUNTIME_VENV_PY = RUNTIME_DIR / "venv" / "bin" / "python"
RUNTIME_APP_ENTRY = RUNTIME_DIR / "app" / "src" / "mac_app_modern.py"

LOG_DIR = Path.home() / "Library" / "Logs" / "Transcript Processor"
LOG_FILE = LOG_DIR / "bootstrap.log"


def log(message: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def _download_with_progress(url: str, dest: Path, progress_cb):
    req = urllib.request.Request(url, headers={"User-Agent": "TranscriptProcessorBootstrap/1.0"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        total = resp.headers.get("Content-Length")
        total = int(total) if total is not None else None
        downloaded = 0
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                progress_cb(downloaded, total)


def _extract_tar(tar_path: Path, dest_dir: Path):
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(dest_dir)


def _clear_quarantine(path: Path) -> None:
    try:
        subprocess.run(
            ["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(path)],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def _chmod_runtime_bin() -> None:
    bin_dir = RUNTIME_DIR / "python" / "bin"
    if not bin_dir.exists():
        return
    try:
        for p in bin_dir.iterdir():
            if p.is_file():
                p.chmod(0o755)
    except Exception:
        pass


def _install_runtime():
    installer = RUNTIME_DIR / "runtime_installer.py"
    reqs = RUNTIME_DIR / "requirements.txt"
    if not installer.exists() or not reqs.exists():
        raise RuntimeError("Runtime installer or requirements.txt missing in payload.")

    cmd = [
        str(RUNTIME_PYTHON),
        str(installer),
        "--runtime-dir",
        str(RUNTIME_DIR),
        "--requirements",
        str(reqs),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(result.stdout or "")
        log(result.stderr or "")
        raise RuntimeError(result.stderr or result.stdout)


def _launch_runtime_app() -> tuple[bool, str]:
    if not RUNTIME_APP_ENTRY.exists():
        return False, f"Runtime app entry not found at {RUNTIME_APP_ENTRY}"

    py = RUNTIME_VENV_PY
    if not py.exists():
        fallback = RUNTIME_DIR / "python" / "bin" / "python3"
        if fallback.exists():
            py = fallback
        else:
            return False, f"Runtime python not found at {RUNTIME_VENV_PY}"

    try:
        env = os.environ.copy()
        app_src = str(RUNTIME_DIR / "app" / "src")
        env["PYTHONPATH"] = app_src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        subprocess.Popen([str(py), str(RUNTIME_APP_ENTRY)], cwd=str(RUNTIME_DIR / "app"), env=env)
        return True, ""
    except Exception as exc:
        return False, f"Failed to launch app: {exc}"


def run_bootstrap_ui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return run_bootstrap_cli()

    q = queue.Queue()
    worker_running = {"value": False}

    def worker():
        worker_running["value"] = True
        try:
            ensure_dirs()
            url = runtime_url()
            payload = APP_SUPPORT_DIR / "runtime_payload.tar.gz"

            def cb(downloaded, total):
                q.put(("progress", downloaded, total))

            log(f"Downloading runtime from {url}")
            q.put(("status", "Downloading runtime..."))
            _download_with_progress(url, payload, cb)
            q.put(("status", "Extracting runtime..."))
            _extract_tar(payload, RUNTIME_DIR)
            _clear_quarantine(RUNTIME_DIR)
            _chmod_runtime_bin()
            q.put(("status", "Installing dependencies..."))
            _install_runtime()
            q.put(("status", "Install complete. Launching app..."))
            q.put(("launch",))
        except Exception as e:
            log("Setup failed.")
            log(str(e))
            log(traceback.format_exc())
            q.put(("error", str(e)))
        finally:
            worker_running["value"] = False

    root = tk.Tk()
    root.title("Transcript Processor — Setup")
    root.geometry("520x200")

    status_var = tk.StringVar(value="Preparing...")
    status = ttk.Label(root, textvariable=status_var)
    status.pack(pady=10)

    prog = ttk.Progressbar(root, mode="determinate", length=420)
    prog.pack(pady=10)

    detail_var = tk.StringVar(value="")
    detail = ttk.Label(root, textvariable=detail_var)
    detail.pack(pady=6)

    def poll():
        try:
            while True:
                msg = q.get_nowait()
                if msg[0] == "status":
                    status_var.set(msg[1])
                elif msg[0] == "progress":
                    downloaded, total = msg[1], msg[2]
                    if total:
                        prog["value"] = (downloaded / total) * 100
                        detail_var.set(f"{downloaded // (1024*1024)} MB / {total // (1024*1024)} MB")
                    else:
                        prog["mode"] = "indeterminate"
                        prog.start(10)
                elif msg[0] == "launch":
                    prog.stop()
                    launched, reason = _launch_runtime_app()
                    if launched:
                        status_var.set("Launching app...")
                        log("Launch succeeded.")
                        root.after(300, root.destroy)
                    else:
                        status_var.set("Setup complete, but launch failed.")
                        log(f"Launch failed: {reason}")
                        detail_var.set(
                            "Could not start the app automatically.\n"
                            "Please reopen the app.\n\n"
                            f"Log: {LOG_FILE}\n\n"
                            f"Reason: {reason}"
                        )
                        retry_btn.config(state="normal")
                        messagebox.showinfo(
                            "Setup Complete",
                            "Dependencies installed successfully.\n\nPlease reopen the app.",
                        )
                elif msg[0] == "error":
                    status_var.set("Setup failed.")
                    detail_var.set(f"{msg[1]}\n\nLog: {LOG_FILE}")
                    retry_btn.config(state="normal")
        except queue.Empty:
            pass
        root.after(200, poll)

    def start_worker():
        if worker_running["value"]:
            return
        retry_btn.config(state="disabled")
        detail_var.set("")
        prog["value"] = 0
        prog["mode"] = "determinate"
        threading.Thread(target=worker, daemon=True).start()

    def open_log_dir():
        try:
            subprocess.run(["/usr/bin/open", str(LOG_DIR)])
        except Exception:
            pass

    retry_btn = ttk.Button(root, text="Retry", command=start_worker, state="disabled")
    retry_btn.pack(pady=4)

    log_btn = ttk.Button(root, text="Open Log Folder", command=open_log_dir)
    log_btn.pack(pady=2)

    start_worker()
    root.after(200, poll)
    root.mainloop()


def run_bootstrap_cli():
    ensure_dirs()
    url = runtime_url()
    payload = APP_SUPPORT_DIR / "runtime_payload.tar.gz"
    print(f"Downloading runtime from {url}...")

    def cb(downloaded, total):
        if total:
            pct = (downloaded / total) * 100
            print(f"{pct:0.1f}%", end="\r")

    _download_with_progress(url, payload, cb)
    print("\nExtracting runtime...")
    _extract_tar(payload, RUNTIME_DIR)
    _clear_quarantine(RUNTIME_DIR)
    _chmod_runtime_bin()
    print("Installing dependencies...")
    _install_runtime()
    print("Launching app...")
    launched, reason = _launch_runtime_app()
    if not launched:
        print("Setup complete. Please reopen the app.")
        print(f"Reason: {reason}")
