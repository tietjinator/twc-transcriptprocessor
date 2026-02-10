from __future__ import annotations

import os
import queue
import threading
import urllib.request
import tarfile
import subprocess
import traceback
import json
import shutil
from datetime import datetime
from pathlib import Path

from .runtime import APP_SUPPORT_DIR, RUNTIME_DIR, RUNTIME_PYTHON, runtime_url, ensure_dirs

RUNTIME_VENV_PY = RUNTIME_DIR / "venv" / "bin" / "python"
RUNTIME_APP_ENTRY = RUNTIME_DIR / "app" / "src" / "mac_app_modern.py"

LOG_DIR = Path.home() / "Library" / "Logs" / "Transcript Processor"
LOG_FILE = LOG_DIR / "bootstrap.log"
HOME_CONFIG_FILE = Path.home() / "TranscriptProcessor" / "config" / "credentials.json"

BREW_PACKAGES = ["ffmpeg", "pango", "cairo", "gdk-pixbuf", "libffi", "glib"]


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


def _find_brew() -> str | None:
    candidates = [
        shutil.which("brew"),
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _open_terminal_with_command(command: str) -> None:
    try:
        safe_cmd = command.replace('"', '\\"')
        osa = (
            'tell application "Terminal"\n'
            f'  do script "{safe_cmd}"\n'
            "  activate\n"
            "end tell"
        )
        subprocess.run(["/usr/bin/osascript", "-e", osa], check=False)
    except Exception:
        pass


def _ensure_system_deps(progress_cb=None):
    brew = _find_brew()
    if not brew:
        raise RuntimeError("BREW_MISSING:Homebrew is required to install system dependencies.")

    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")

    missing = []
    for pkg in BREW_PACKAGES:
        try:
            result = subprocess.run([brew, "list", pkg], env=env, capture_output=True, text=True)
            if result.returncode != 0:
                missing.append(pkg)
        except Exception:
            missing.append(pkg)

    if not missing:
        return

    total = len(missing)
    for idx, pkg in enumerate(missing, start=1):
        if progress_cb:
            progress_cb(idx, total, f"Installing {pkg}...")
        proc = subprocess.Popen(
            [brew, "install", pkg],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if proc.stdout:
            for line in proc.stdout:
                log(line.rstrip())
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"Failed to install {pkg} via Homebrew.")


def _load_credentials() -> dict:
    if HOME_CONFIG_FILE.exists():
        try:
            with open(HOME_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_credentials(anthropic_key: str, openai_key: str | None) -> None:
    config = _load_credentials()
    config["anthropic_api_key"] = anthropic_key
    if openai_key:
        config["openai_api_key"] = openai_key
    HOME_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HOME_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    try:
        HOME_CONFIG_FILE.chmod(0o600)
    except Exception:
        pass


def _install_runtime(progress_cb=None):
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
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last_lines = []
    if proc.stdout:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                log(line)
                last_lines.append(line)
                if len(last_lines) > 20:
                    last_lines.pop(0)
                if line.startswith("TPP_STEP:") and progress_cb:
                    try:
                        payload = line.split("TPP_STEP:", 1)[1]
                        step_part, msg = payload.split(":", 1)
                        step, total = step_part.split("/", 1)
                        progress_cb(int(step), int(total), msg.strip())
                    except Exception:
                        pass
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError("\n".join(last_lines) or "Runtime install failed.")


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

        tcl_dir = RUNTIME_DIR / "python" / "lib" / "tcl9.0"
        tk_dir = RUNTIME_DIR / "python" / "lib" / "tk9.0"
        if tcl_dir.exists():
            env["TCL_LIBRARY"] = str(tcl_dir)
        if tk_dir.exists():
            env["TK_LIBRARY"] = str(tk_dir)
        fallback_libs = ["/opt/homebrew/lib", "/usr/local/lib"]
        existing = env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(fallback_libs + ([existing] if existing else []))

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
            def install_cb(step, total, message):
                q.put(("install_step", step, total, message))
            _install_runtime(install_cb)
            q.put(("status", "Installing system dependencies..."))
            def sys_cb(step, total, message):
                q.put(("system_step", step, total, message))
            _ensure_system_deps(sys_cb)
            q.put(("status", "Install complete. Launching app..."))
            q.put(("launch",))
        except Exception as e:
            log("Setup failed.")
            log(str(e))
            log(traceback.format_exc())
            msg = str(e)
            if msg.startswith("BREW_MISSING:"):
                q.put(("brew_missing",))
                msg = msg.split("BREW_MISSING:", 1)[1]
            q.put(("error", msg))
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

    def ensure_api_keys() -> bool:
        cfg = _load_credentials()
        anthropic_key = (cfg.get("anthropic_api_key") or "").strip()
        if anthropic_key.startswith("sk-ant-"):
            return True

        dialog = tk.Toplevel(root)
        dialog.title("API Keys Required")
        dialog.geometry("520x300")
        dialog.configure(bg="#f5f5f7")
        dialog.transient(root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Anthropic API key not found.",
            font=("SF Pro Display", 15, "bold"),
            bg="#f5f5f7"
        ).pack(pady=(18, 6))

        tk.Label(
            dialog,
            text="Enter your keys below to continue.",
            font=("SF Pro Display", 11),
            bg="#f5f5f7",
            fg="#555"
        ).pack(pady=(0, 12))

        form = tk.Frame(dialog, bg="#f5f5f7")
        form.pack(padx=20, pady=6, fill=tk.X)

        tk.Label(form, text="Anthropic API Key", font=("SF Pro Display", 11), bg="#f5f5f7").grid(row=0, column=0, sticky="w", pady=4)
        anthropic_entry = tk.Entry(form, width=48, show="*", font=("SF Pro Display", 11))
        anthropic_entry.grid(row=1, column=0, sticky="we", pady=(0, 8))

        tk.Label(form, text="OpenAI API Key (optional)", font=("SF Pro Display", 11), bg="#f5f5f7").grid(row=2, column=0, sticky="w", pady=4)
        openai_entry = tk.Entry(form, width=48, show="*", font=("SF Pro Display", 11))
        openai_entry.grid(row=3, column=0, sticky="we")

        form.columnconfigure(0, weight=1)

        result = {"saved": False}

        def on_save():
            anthropic_val = anthropic_entry.get().strip()
            openai_val = openai_entry.get().strip()

            if not anthropic_val:
                messagebox.showerror("API Key Required", "Anthropic API key is required.", parent=dialog)
                return

            if not anthropic_val.startswith("sk-ant-"):
                proceed = messagebox.askyesno(
                    "Confirm Key",
                    "Anthropic key does not start with 'sk-ant-'. Continue anyway?",
                    parent=dialog
                )
                if not proceed:
                    return

            if openai_val and not openai_val.startswith("sk-"):
                proceed = messagebox.askyesno(
                    "Confirm Key",
                    "OpenAI key does not start with 'sk-'. Continue anyway?",
                    parent=dialog
                )
                if not proceed:
                    return

            _save_credentials(anthropic_val, openai_val or None)
            result["saved"] = True
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#f5f5f7")
        btn_frame.pack(pady=18)

        save_btn = tk.Button(
            btn_frame,
            text="Save",
            command=on_save,
            font=("SF Pro Display", 12),
            bg="#007AFF",
            fg="white",
            padx=24,
            pady=8,
            relief=tk.FLAT,
            cursor="hand2"
        )
        save_btn.pack(side=tk.LEFT, padx=6)

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            command=on_cancel,
            font=("SF Pro Display", 12),
            bg="#E0E0E0",
            fg="#333",
            padx=24,
            pady=8,
            relief=tk.FLAT,
            cursor="hand2"
        )
        cancel_btn.pack(side=tk.LEFT, padx=6)

        dialog.wait_window()
        return result["saved"]

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
                elif msg[0] == "install_step":
                    step, total, message = msg[1], msg[2], msg[3]
                    prog.stop()
                    prog["mode"] = "determinate"
                    prog["value"] = (step / total) * 100 if total else 0
                    detail_var.set(message)
                elif msg[0] == "system_step":
                    step, total, message = msg[1], msg[2], msg[3]
                    prog.stop()
                    prog["mode"] = "determinate"
                    prog["value"] = (step / total) * 100 if total else 0
                    detail_var.set(message)
                elif msg[0] == "brew_missing":
                    retry_btn.config(state="normal")
                    brew_btn.config(state="normal")
                elif msg[0] == "launch":
                    prog.stop()
                    if not ensure_api_keys():
                        status_var.set("Setup complete, but API key missing.")
                        detail_var.set(f"Anthropic API key required.\n\nLog: {LOG_FILE}")
                        retry_btn.config(state="normal")
                        continue
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

    def install_homebrew():
        cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        _open_terminal_with_command(cmd)

    retry_btn = ttk.Button(root, text="Retry", command=start_worker, state="disabled")
    retry_btn.pack(pady=4)

    brew_btn = ttk.Button(root, text="Install Homebrew", command=install_homebrew, state="disabled")
    brew_btn.pack(pady=2)

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
    print("Installing system dependencies...")
    _ensure_system_deps()
    cfg = _load_credentials()
    if not (cfg.get("anthropic_api_key") or "").startswith("sk-ant-"):
        key = input("Enter your Anthropic API key (sk-ant-...): ").strip()
        if key:
            openai = input("Enter your OpenAI API key (optional, sk-...): ").strip()
            _save_credentials(key, openai or None)
    print("Launching app...")
    launched, reason = _launch_runtime_app()
    if not launched:
        print("Setup complete. Please reopen the app.")
        print(f"Reason: {reason}")
