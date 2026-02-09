from __future__ import annotations

import os
import queue
import threading
import urllib.request
import zipfile
import subprocess
from pathlib import Path

from .runtime import APP_SUPPORT_DIR, RUNTIME_DIR, RUNTIME_PYTHON, runtime_url, ensure_dirs


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


def _extract_zip(zip_path: Path, dest_dir: Path):
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


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
        raise RuntimeError(result.stderr or result.stdout)


def run_bootstrap_ui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return run_bootstrap_cli()

    q = queue.Queue()

    def worker():
        try:
            ensure_dirs()
            url = runtime_url()
            payload = APP_SUPPORT_DIR / "runtime_payload.zip"

            def cb(downloaded, total):
                q.put(("progress", downloaded, total))

            q.put(("status", f"Downloading runtime..."))
            _download_with_progress(url, payload, cb)
            q.put(("status", "Extracting runtime..."))
            _extract_zip(payload, RUNTIME_DIR)
            q.put(("status", "Installing dependencies..."))
            _install_runtime()
            q.put(("status", "Install complete."))
            q.put(("done",))
        except Exception as e:
            q.put(("error", str(e)))

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
                elif msg[0] == "done":
                    status_var.set("Setup complete. You can reopen the app.")
                    prog.stop()
                    messagebox.showinfo(
                        "Setup Complete",
                        "Dependencies installed successfully.\n\nPlease reopen the app.",
                    )
                elif msg[0] == "error":
                    status_var.set("Setup failed.")
                    detail_var.set(msg[1])
        except queue.Empty:
            pass
        root.after(200, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(200, poll)
    root.mainloop()


def run_bootstrap_cli():
    ensure_dirs()
    url = runtime_url()
    payload = APP_SUPPORT_DIR / "runtime_payload.zip"
    print(f"Downloading runtime from {url}...")

    def cb(downloaded, total):
        if total:
            pct = (downloaded / total) * 100
            print(f"{pct:0.1f}%", end="\r")

    _download_with_progress(url, payload, cb)
    print("\nExtracting runtime...")
    _extract_zip(payload, RUNTIME_DIR)
    print("Installing dependencies...")
    _install_runtime()
    print("Setup complete. Please reopen the app.")
