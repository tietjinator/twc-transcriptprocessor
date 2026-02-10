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


def _install_runtime(progress_cb=None, download_cb=None):
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
                if line.startswith("TPP_DOWNLOAD:") and download_cb:
                    try:
                        payload = line.split("TPP_DOWNLOAD:", 1)[1]
                        step_part, pct_part = payload.split(":", 1)
                        done, total = step_part.split("/", 1)
                        download_cb(int(done), int(total), int(pct_part))
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
        model_cache = RUNTIME_DIR / "models" / "huggingface"
        env["HUGGINGFACE_HUB_CACHE"] = str(model_cache)
        env["HF_HOME"] = str(model_cache)

        subprocess.Popen([str(py), str(RUNTIME_APP_ENTRY)], cwd=str(RUNTIME_DIR / "app"), env=env)
        return True, ""
    except Exception as exc:
        return False, f"Failed to launch app: {exc}"


def run_bootstrap_ui():
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return run_bootstrap_cli()

    class ModernButton(tk.Canvas):
        """Rounded button similar to the main app UI."""

        def __init__(
            self,
            parent,
            text,
            command,
            bg_color="#007AFF",
            text_color="white",
            hover_color=None,
            disabled_color="#E0E0E0",
            disabled_text="#A0A0A0",
            font_size=12,
            padx=26,
            pady=10,
        ):
            super().__init__(parent, highlightthickness=0, bg=parent["bg"])
            self.command = command
            self.bg_color = bg_color
            self.text_color = text_color
            self.hover_color = hover_color or self._adjust_color(bg_color, 0.9)
            self.disabled_color = disabled_color
            self.disabled_text = disabled_text
            self.enabled = True

            text_width = len(text) * (font_size * 0.6)
            width = int(text_width + padx * 2)
            height = int(font_size + pady * 2)
            self.config(width=width, height=height)

            radius = 8
            self.rect = self.create_rounded_rectangle(
                0, 0, width, height, radius=radius, fill=bg_color, outline=""
            )
            self.text_id = self.create_text(
                width / 2,
                height / 2,
                text=text,
                fill=text_color,
                font=("SF Pro Display", font_size, "bold"),
            )

            self.tag_bind(self.rect, "<Enter>", self._on_enter)
            self.tag_bind(self.text_id, "<Enter>", self._on_enter)
            self.tag_bind(self.rect, "<Leave>", self._on_leave)
            self.tag_bind(self.text_id, "<Leave>", self._on_leave)
            self.tag_bind(self.rect, "<Button-1>", self._on_click)
            self.tag_bind(self.text_id, "<Button-1>", self._on_click)

        def create_rounded_rectangle(self, x1, y1, x2, y2, radius=8, **kwargs):
            points = [
                x1 + radius, y1,
                x1 + radius, y1,
                x2 - radius, y1,
                x2 - radius, y1,
                x2, y1,
                x2, y1 + radius,
                x2, y1 + radius,
                x2, y2 - radius,
                x2, y2 - radius,
                x2, y2,
                x2 - radius, y2,
                x2 - radius, y2,
                x1 + radius, y2,
                x1 + radius, y2,
                x1, y2,
                x1, y2 - radius,
                x1, y2 - radius,
                x1, y1 + radius,
                x1, y1 + radius,
                x1, y1,
            ]
            return self.create_polygon(points, smooth=True, **kwargs)

        def _adjust_color(self, color, factor):
            color = color.lstrip("#")
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)
            return f"#{r:02x}{g:02x}{b:02x}"

        def set_enabled(self, enabled: bool):
            self.enabled = enabled
            if enabled:
                self.itemconfig(self.rect, fill=self.bg_color)
                self.itemconfig(self.text_id, fill=self.text_color)
            else:
                self.itemconfig(self.rect, fill=self.disabled_color)
                self.itemconfig(self.text_id, fill=self.disabled_text)

        def _on_enter(self, _event=None):
            if not self.enabled:
                return
            self.itemconfig(self.rect, fill=self.hover_color)
            self.config(cursor="hand2")

        def _on_leave(self, _event=None):
            if not self.enabled:
                return
            self.itemconfig(self.rect, fill=self.bg_color)
            self.config(cursor="")

        def _on_click(self, _event=None):
            if self.enabled and self.command:
                self.command()

    class RoundedProgress(tk.Canvas):
        def __init__(
            self,
            master,
            width=420,
            height=14,
            radius=7,
            bg_color="#e5e7eb",
            fg_color="#0A84FF",
        ):
            super().__init__(
                master,
                width=width,
                height=height,
                bg=master["bg"],
                highlightthickness=0,
                bd=0,
                relief=tk.FLAT,
            )
            self._width = width
            self._height = height
            self._radius = radius
            self._bg_color = bg_color
            self._fg_color = fg_color
            self._value = 0
            self._max = 100
            self._animating = False
            self._anim_pos = 0
            self._anim_interval = 20
            self._draw_determinate()

        def _draw_round(self, x1, y1, x2, y2, radius, color):
            radius = max(0, min(radius, (y2 - y1) / 2, (x2 - x1) / 2))
            if x2 - x1 <= 0:
                return
            if radius <= 0:
                self.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                return
            self.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=color, outline="")
            self.create_oval(x1, y1, x1 + 2 * radius, y2, fill=color, outline="")
            self.create_oval(x2 - 2 * radius, y1, x2, y2, fill=color, outline="")

        def _draw_determinate(self):
            self.delete("all")
            self._draw_round(0, 0, self._width, self._height, self._radius, self._bg_color)
            if self._max <= 0:
                return
            fill_w = int(self._width * (self._value / self._max))
            if fill_w <= 0:
                return
            if fill_w < self._height:
                self.create_oval(0, 0, fill_w, self._height, fill=self._fg_color, outline="")
            else:
                self._draw_round(0, 0, fill_w, self._height, self._radius, self._fg_color)

        def set(self, value, maximum=100):
            self._value = max(0, min(value, maximum))
            self._max = max(1, maximum)
            self._animating = False
            self._draw_determinate()

        def start(self, interval=20):
            self._anim_interval = interval
            if self._animating:
                return
            self._animating = True
            self._animate()

        def stop(self):
            self._animating = False

        def _animate(self):
            if not self._animating:
                return
            self.delete("all")
            self._draw_round(0, 0, self._width, self._height, self._radius, self._bg_color)
            seg_w = int(self._width * 0.28)
            self._anim_pos = (self._anim_pos + 10) % (self._width + seg_w)
            start_x = self._anim_pos - seg_w
            end_x = start_x + seg_w
            draw_start = max(0, start_x)
            draw_end = min(self._width, end_x)
            if draw_end > 0:
                if draw_end - draw_start < self._height:
                    self.create_oval(draw_start, 0, draw_end, self._height, fill=self._fg_color, outline="")
                else:
                    self._draw_round(draw_start, 0, draw_end, self._height, self._radius, self._fg_color)
            self.after(self._anim_interval, self._animate)

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
            def download_cb(done, total, pct):
                q.put(("install_download", done, total, pct))
            _install_runtime(install_cb, download_cb)
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
    root.geometry("520x360")
    root.minsize(520, 360)
    root.configure(bg="#f5f5f7")

    status_var = tk.StringVar(value="Preparing...")
    status = tk.Label(
        root,
        textvariable=status_var,
        font=("SF Pro Display", 14, "bold"),
        bg="#f5f5f7",
        fg="#1d1d1f",
    )
    status.pack(pady=(14, 8))

    prog = RoundedProgress(root, width=420, height=14, radius=7)
    prog.pack(pady=(4, 12))

    phase_var = tk.StringVar(value="")
    phase = tk.Label(
        root,
        textvariable=phase_var,
        font=("SF Pro Display", 12),
        bg="#f5f5f7",
        fg="#555",
    )
    phase.pack(pady=(0, 6))

    detail_var = tk.StringVar(value="")
    detail = tk.Label(
        root,
        textvariable=detail_var,
        font=("SF Pro Display", 11),
        bg="#f5f5f7",
        fg="#555",
    )
    detail.pack(pady=(0, 4))

    def ensure_api_keys() -> bool:
        cfg = _load_credentials()
        anthropic_key = (cfg.get("anthropic_api_key") or "").strip()
        if anthropic_key.startswith("sk-ant-"):
            return True

        dialog = tk.Toplevel(root)
        dialog.title("API Keys Required")
        dialog.geometry("560x340")
        dialog.configure(bg="#f5f5f7")
        dialog.transient(root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="Anthropic API key not found.",
            font=("SF Pro Display", 15, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
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

        tk.Label(form, text="Anthropic API Key", font=("SF Pro Display", 11), bg="#f5f5f7", fg="#1d1d1f").grid(row=0, column=0, sticky="w", pady=4)
        anthropic_entry = tk.Entry(
            form,
            width=48,
            show="*",
            font=("SF Pro Display", 11),
            bg="white",
            fg="#1d1d1f",
            insertbackground="#1d1d1f",
            highlightthickness=1,
            highlightbackground="#d0d0d0",
            highlightcolor="#007AFF",
            relief=tk.FLAT,
        )
        anthropic_entry.grid(row=1, column=0, sticky="we", pady=(0, 8))

        tk.Label(form, text="OpenAI API Key (optional)", font=("SF Pro Display", 11), bg="#f5f5f7", fg="#1d1d1f").grid(row=2, column=0, sticky="w", pady=4)
        openai_entry = tk.Entry(
            form,
            width=48,
            show="*",
            font=("SF Pro Display", 11),
            bg="white",
            fg="#1d1d1f",
            insertbackground="#1d1d1f",
            highlightthickness=1,
            highlightbackground="#d0d0d0",
            highlightcolor="#007AFF",
            relief=tk.FLAT,
        )
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

        save_btn = ModernButton(
            btn_frame,
            text="Save",
            command=on_save,
            bg_color="#007AFF",
            text_color="white",
            font_size=12,
            padx=28,
            pady=10,
        )
        save_btn.pack(side=tk.LEFT, padx=8)

        cancel_btn = ModernButton(
            btn_frame,
            text="Cancel",
            command=on_cancel,
            bg_color="#E0E0E0",
            text_color="#1d1d1f",
            hover_color="#d5d5d5",
            font_size=12,
            padx=28,
            pady=10,
        )
        cancel_btn.pack(side=tk.LEFT, padx=8)

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
                        prog.stop()
                        prog.set((downloaded / total) * 100)
                        phase_var.set("Downloading runtime...")
                        detail_var.set(f"{downloaded // (1024*1024)} MB / {total // (1024*1024)} MB")
                    else:
                        phase_var.set("Downloading runtime...")
                        detail_var.set("")
                        prog.start(20)
                elif msg[0] == "install_step":
                    step, total, message = msg[1], msg[2], msg[3]
                    prog.stop()
                    if message.lower().startswith("downloading parakeet model"):
                        prog.set(0)
                        phase_var.set(message)
                        detail_var.set("")
                    else:
                        prog.set((step / total) * 100 if total else 0)
                        phase_var.set(message)
                        detail_var.set("")
                elif msg[0] == "system_step":
                    step, total, message = msg[1], msg[2], msg[3]
                    prog.stop()
                    prog.set((step / total) * 100 if total else 0)
                    phase_var.set(message)
                    detail_var.set("")
                elif msg[0] == "install_download":
                    done, total, pct = msg[1], msg[2], msg[3]
                    prog.stop()
                    prog.set(pct)
                    phase_var.set("Downloading Parakeet model...")
                    if total >= 1024 * 1024:
                        detail_var.set(f"{pct}% • {done // (1024*1024)} MB / {total // (1024*1024)} MB")
                    else:
                        detail_var.set(f"{pct}% • {done} / {total} files")
                elif msg[0] == "brew_missing":
                    _show_retry(True)
                    _show_brew(True)
                    retry_btn.set_enabled(True)
                    brew_btn.set_enabled(True)
                elif msg[0] == "launch":
                    prog.stop()
                    if not ensure_api_keys():
                        status_var.set("Setup complete, but API key missing.")
                        phase_var.set("")
                        detail_var.set(f"Anthropic API key required.\n\nLog: {LOG_FILE}")
                        _show_retry(True)
                        retry_btn.set_enabled(True)
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
                        _show_retry(True)
                        retry_btn.set_enabled(True)
                        messagebox.showinfo(
                            "Setup Complete",
                            "Dependencies installed successfully.\n\nPlease reopen the app.",
                        )
                elif msg[0] == "error":
                    status_var.set("Setup failed.")
                    phase_var.set("")
                    detail_var.set(f"{msg[1]}\n\nLog: {LOG_FILE}")
                    _show_retry(True)
                    retry_btn.set_enabled(True)
        except queue.Empty:
            pass
        root.after(200, poll)

    def start_worker():
        if worker_running["value"]:
            return
        _show_retry(False)
        _show_brew(False)
        retry_btn.set_enabled(False)
        brew_btn.set_enabled(False)
        phase_var.set("")
        detail_var.set("")
        prog.set(0)
        threading.Thread(target=worker, daemon=True).start()

    def open_log_dir():
        try:
            subprocess.run(["/usr/bin/open", str(LOG_DIR)])
        except Exception:
            pass

    def install_homebrew():
        cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        _open_terminal_with_command(cmd)

    btn_frame = tk.Frame(root, bg="#f5f5f7")
    btn_frame.pack(pady=(2, 10))

    retry_btn = ModernButton(
        btn_frame,
        text="Retry",
        command=start_worker,
        bg_color="#E0E0E0",
        text_color="#1d1d1f",
        hover_color="#d5d5d5",
        font_size=12,
        padx=26,
        pady=8,
    )
    retry_btn.pack(pady=4)
    retry_btn.set_enabled(False)

    brew_btn = ModernButton(
        btn_frame,
        text="Install Homebrew",
        command=install_homebrew,
        bg_color="#E0E0E0",
        text_color="#1d1d1f",
        hover_color="#d5d5d5",
        font_size=12,
        padx=26,
        pady=8,
    )
    brew_btn.pack(pady=4)
    brew_btn.set_enabled(False)

    log_btn = ModernButton(
        btn_frame,
        text="Open Log Folder",
        command=open_log_dir,
        bg_color="#E0E0E0",
        text_color="#1d1d1f",
        hover_color="#d5d5d5",
        font_size=12,
        padx=26,
        pady=8,
    )
    log_btn.pack(pady=4)

    def _show_retry(show: bool):
        if show:
            if not retry_btn.winfo_ismapped():
                retry_btn.pack(pady=4)
        elif retry_btn.winfo_ismapped():
            retry_btn.pack_forget()

    def _show_brew(show: bool):
        if show:
            if not brew_btn.winfo_ismapped():
                brew_btn.pack(pady=4)
        elif brew_btn.winfo_ismapped():
            brew_btn.pack_forget()

    _show_retry(False)
    _show_brew(False)

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
