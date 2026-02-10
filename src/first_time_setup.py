#!/usr/bin/env python3
"""
First-Time Setup Wizard for Transcript Processor
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext
import subprocess
import json
from pathlib import Path
import os
import sys
import threading


class ModernButton(tk.Canvas):
    """Custom modern button that works reliably on macOS"""

    def __init__(self, parent, text, command, bg_color="#007AFF", text_color="white",
                 font_size=14, padx=30, pady=12):
        super().__init__(parent, highlightthickness=0)

        self.command = command
        self.bg_color = bg_color
        self.hover_color = self._adjust_color(bg_color, 0.9)
        self.text_color = text_color
        self.text = text

        # Calculate size based on text
        padding_x = padx
        padding_y = pady

        # Estimate button size
        text_width = len(text) * (font_size * 0.6)
        width = int(text_width + padding_x * 2)
        height = int(font_size + padding_y * 2)

        self.config(width=width, height=height, bg=parent['bg'])

        # Draw button with rounded corners
        radius = 8
        self.rect = self.create_rounded_rectangle(
            0, 0, width, height,
            radius=radius,
            fill=bg_color,
            outline="",
            tags="button"
        )

        self.text_id = self.create_text(
            width/2, height/2,
            text=text,
            fill=text_color,
            font=("SF Pro Display", font_size, "bold"),
            tags="button"
        )

        # Bind events
        self.tag_bind("button", "<Enter>", self._on_enter)
        self.tag_bind("button", "<Leave>", self._on_leave)
        self.tag_bind("button", "<Button-1>", self._on_click)

    def create_rounded_rectangle(self, x1, y1, x2, y2, radius=8, **kwargs):
        """Create a rounded rectangle"""
        points = [
            x1+radius, y1,
            x1+radius, y1,
            x2-radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1+radius,
            x1, y1
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _adjust_color(self, color, factor):
        """Darken or lighten a color"""
        try:
            # Remove # if present
            color = color.lstrip('#')
            # Convert to RGB
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            # Adjust
            r, g, b = int(r * factor), int(g * factor), int(b * factor)
            # Convert back
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return color

    def _on_enter(self, event):
        self.itemconfig(self.rect, fill=self.hover_color)
        self.config(cursor="hand2")

    def _on_leave(self, event):
        self.itemconfig(self.rect, fill=self.bg_color)
        self.config(cursor="")

    def _on_click(self, event):
        if self.command:
            self.command()


class SetupWizard:
    """First-time setup wizard for configuring Transcript Processor"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Transcript Processor - First Time Setup")
        self.root.geometry("700x650")
        self.root.configure(bg="#f5f5f7")
        self.root.resizable(False, False)

        # Setup data
        self.config = {
            'anthropic_api_key': '',
            'openai_api_key': '',
            'whisper_mode': 'remote',  # 'remote' or 'local'
            'whisper_host': '',
            'whisper_port': 5687
        }

        self.current_step = 0
        self.steps = [
            self.show_welcome,
            self.check_ffmpeg,
            self.setup_api_key,
            self.setup_openai_key,
            self.setup_whisper,
            self.show_complete
        ]

        # Main container
        self.main_frame = tk.Frame(self.root, bg="#f5f5f7")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)

        # Show first step
        self.show_step()

    def show_step(self):
        """Display current setup step"""
        # Clear main frame
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        # Show current step
        self.steps[self.current_step]()

    def next_step(self):
        """Move to next step"""
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self.show_step()

    def prev_step(self):
        """Move to previous step"""
        if self.current_step > 0:
            self.current_step -= 1
            self.show_step()

    def show_welcome(self):
        """Welcome screen"""
        tk.Label(
            self.main_frame,
            text="Welcome to Transcript Processor",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=10)

        tk.Label(
            self.main_frame,
            text="Let's get you set up!",
            font=("SF Pro Display", 14),
            bg="#f5f5f7",
            fg="#86868b"
        ).pack(pady=15)

        info_text = """This wizard will help you configure Transcript Processor.

We'll check for required dependencies and set up:
  • FFmpeg (for audio/video conversion)
  • WeasyPrint (for PDF generation)
  • Anthropic API key (for Claude AI)
  • OpenAI API key (for GPT models, optional)
  • Parakeet-MLX (for local transcription, optional)

Required:
  - FFmpeg, WeasyPrint, Anthropic API key

Optional:
  - OpenAI API key (for GPT-4o mini / GPT-5 nano)
  - Parakeet-MLX (for faster local transcription)

This will only take a few minutes."""

        tk.Label(
            self.main_frame,
            text=info_text,
            font=("SF Pro Display", 12),
            bg="#f5f5f7",
            fg="#1d1d1f",
            justify=tk.LEFT
        ).pack(pady=20)

        # Next button
        ModernButton(
            self.main_frame,
            text="Get Started",
            command=self.next_step,
            bg_color="#007AFF",
            text_color="white",
            font_size=16,
            padx=50,
            pady=15
        ).pack(pady=20)

    def check_ffmpeg(self):
        """Check for FFmpeg installation"""
        tk.Label(
            self.main_frame,
            text="Step 1: Dependencies",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=5)

        tk.Label(
            self.main_frame,
            text="Checking for required dependencies...",
            font=("SF Pro Display", 12),
            bg="#f5f5f7",
            fg="#86868b"
        ).pack(pady=15)

        def _has_brew():
            try:
                subprocess.run(["brew", "--version"], capture_output=True, check=True, timeout=2)
                return True
            except Exception:
                return False

        def _open_terminal_install(command: str):
            """Open Terminal and run a Homebrew install command."""
            try:
                subprocess.run([
                    "osascript",
                    "-e",
                    f'tell application "Terminal" to do script "{command}"'
                ], check=False)
            except Exception:
                pass

        # Check FFmpeg
        ffmpeg_paths = [
            'ffmpeg',
            '/opt/homebrew/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            '/usr/bin/ffmpeg'
        ]

        ffmpeg_found = False
        ffmpeg_path = None
        for path in ffmpeg_paths:
            try:
                subprocess.run([path, '-version'], capture_output=True, check=True, timeout=2)
                ffmpeg_found = True
                ffmpeg_path = path
                break
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        # Check WeasyPrint
        weasyprint_found = False
        try:
            import weasyprint  # noqa: F401
            weasyprint_found = True
        except Exception:
            weasyprint_found = False

        # Check Parakeet-MLX (optional but recommended)
        parakeet_found = False
        try:
            import parakeet_mlx  # noqa: F401
            parakeet_found = True
        except Exception:
            parakeet_found = False

        # Status frame
        status_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT, borderwidth=0)
        status_frame.pack(fill=tk.X, pady=15)
        status_label = tk.Label(
            self.main_frame,
            text="",
            font=("SF Pro Display", 11),
            bg="#f5f5f7",
            fg="#1d1d1f"
        )
        status_label.pack(pady=6)

        if ffmpeg_found:
            # Success
            tk.Label(
                status_frame,
                text="✓ FFmpeg found!",
                font=("SF Pro Display", 14, "bold"),
                bg="white",
                fg="#0d5c2d",
                padx=20,
                pady=15
            ).pack()

            tk.Label(
                status_frame,
                text=f"Location: {ffmpeg_path}",
                font=("SF Mono", 11),
                bg="white",
                fg="#86868b",
                padx=20,
                pady=10
            ).pack()
        else:
            # Not found
            tk.Label(
                status_frame,
                text="✗ FFmpeg not found",
                font=("SF Pro Display", 14, "bold"),
                bg="white",
                fg="#a41c27",
                padx=20,
                pady=15
            ).pack()

            install_text = """FFmpeg is required to convert audio/video files.

Install FFmpeg using Homebrew:
  brew install ffmpeg

Or download from: https://ffmpeg.org/download.html"""

            tk.Label(
                status_frame,
                text=install_text,
                font=("SF Pro Display", 11),
                bg="white",
                fg="#1d1d1f",
                justify=tk.LEFT,
                padx=20,
                pady=10
            ).pack()

            def install_ffmpeg():
                """Attempt to install FFmpeg via Homebrew."""
                if not _has_brew():
                    status_label.config(text="Homebrew not found. Install from https://brew.sh")
                    return

                status_label.config(text="Installing FFmpeg... (this may take a few minutes)")

                def _run():
                    try:
                        result = subprocess.run(
                            ["brew", "install", "ffmpeg"],
                            check=False,
                            capture_output=True,
                            text=True,
                            env={**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")}
                        )
                        if result.returncode == 0:
                            self.root.after(0, lambda: status_label.config(text="FFmpeg installed. Re-checking..."))
                            self.root.after(0, self.show_step)
                        else:
                            err = (result.stderr or result.stdout or "").strip()
                            def _fail():
                                status_label.config(text="FFmpeg install failed. See details.")
                                messagebox.showerror(
                                    "FFmpeg Install Failed",
                                    "Homebrew could not install FFmpeg.\n\n"
                                    "This may require your password or Terminal permissions.\n\n"
                                    f"Details:\n{err[:800]}\n\n"
                                    "You can also run in Terminal:\n  brew install ffmpeg"
                                )
                            self.root.after(0, _fail)
                    except Exception as e:
                        def _fail_ex():
                            status_label.config(text="FFmpeg install failed. See details.")
                            messagebox.showerror(
                                "FFmpeg Install Failed",
                                f"{e}\n\nTry running in Terminal:\n  brew install ffmpeg"
                            )
                        self.root.after(0, _fail_ex)

                threading.Thread(target=_run, daemon=True).start()

        if weasyprint_found:
            tk.Label(
                status_frame,
                text="✓ WeasyPrint found!",
                font=("SF Pro Display", 14, "bold"),
                bg="white",
                fg="#0d5c2d",
                padx=20,
                pady=15
            ).pack()
        else:
            tk.Label(
                status_frame,
                text="✗ WeasyPrint not found",
                font=("SF Pro Display", 14, "bold"),
                bg="white",
                fg="#a41c27",
                padx=20,
                pady=15
            ).pack()

            install_text = """WeasyPrint is required for PDF generation.

Install WeasyPrint dependencies and Python package:
  1. brew install pango cairo gdk-pixbuf libffi
  2. Then install via pip in your venv"""

            tk.Label(
                status_frame,
                text=install_text,
                font=("SF Pro Display", 11),
                bg="white",
                fg="#1d1d1f",
                justify=tk.LEFT,
                padx=20,
                pady=10
            ).pack()

            def install_weasyprint():
                """Attempt to install WeasyPrint system dependencies and Python package."""
                if not _has_brew():
                    status_label.config(text="Homebrew not found. Install from https://brew.sh")
                    return
                status_label.config(text="Installing WeasyPrint dependencies... (this may take a few minutes)")

                def _run():
                    try:
                        # First install Homebrew system dependencies
                        result = subprocess.run(
                            ["brew", "install", "pango", "cairo", "gdk-pixbuf", "libffi"],
                            check=False,
                            capture_output=True,
                            text=True,
                            env={**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")}
                        )
                        if result.returncode != 0:
                            err = (result.stderr or result.stdout or "").strip()
                            def _fail():
                                status_label.config(text="System dependencies install failed. See details.")
                                messagebox.showerror(
                                    "Dependency Install Failed",
                                    "Could not install system dependencies for WeasyPrint.\n\n"
                                    f"Details:\n{err[:800]}\n\n"
                                    "You can try in Terminal:\n  brew install pango cairo gdk-pixbuf libffi"
                                )
                            self.root.after(0, _fail)
                            return

                        # Now install WeasyPrint via pip
                        self.root.after(0, lambda: status_label.config(text="Installing WeasyPrint Python package..."))

                        # Find the venv python
                        venv_python = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python3.14"
                        if not venv_python.exists():
                            venv_python = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python3"
                        if not venv_python.exists():
                            venv_python = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python"

                        pip_result = subprocess.run(
                            [str(venv_python), "-m", "pip", "install", "weasyprint"],
                            check=False,
                            capture_output=True,
                            text=True
                        )

                        if pip_result.returncode == 0:
                            self.root.after(0, lambda: status_label.config(text="WeasyPrint installed. Re-checking..."))
                            self.root.after(0, self.show_step)
                        else:
                            err = (pip_result.stderr or pip_result.stdout or "").strip()
                            def _fail():
                                status_label.config(text="WeasyPrint install failed. See details.")
                                messagebox.showerror(
                                    "WeasyPrint Install Failed",
                                    "Could not install WeasyPrint Python package.\n\n"
                                    f"Details:\n{err[:800]}\n\n"
                                    "You can try in Terminal:\n  ./venv/bin/pip install weasyprint"
                                )
                            self.root.after(0, _fail)
                    except Exception as e:
                        def _fail_ex():
                            status_label.config(text="WeasyPrint install failed. See details.")
                            messagebox.showerror(
                                "WeasyPrint Install Failed",
                                f"{e}\n\nTry running in Terminal:\n  brew install pango cairo gdk-pixbuf libffi\n  ./venv/bin/pip install weasyprint"
                            )
                        self.root.after(0, _fail_ex)

                threading.Thread(target=_run, daemon=True).start()

        # Parakeet-MLX status (optional)
        if parakeet_found:
            tk.Label(
                status_frame,
                text="✓ Parakeet-MLX found (local transcription available)",
                font=("SF Pro Display", 12),
                bg="white",
                fg="#0d5c2d",
                padx=20,
                pady=10
            ).pack()
        else:
            tk.Label(
                status_frame,
                text="ℹ️ Parakeet-MLX not found (optional - faster local transcription)",
                font=("SF Pro Display", 12),
                bg="white",
                fg="#86868b",
                padx=20,
                pady=10
            ).pack()

        # Always show buttons after status (whether found or not found)
        btn_container = tk.Frame(self.main_frame, bg="#f5f5f7")
        btn_container.pack(fill=tk.X, pady=20)

        all_required_found = ffmpeg_found and weasyprint_found

        if all_required_found:
            # Next button
            ModernButton(
                btn_container,
                text="Continue",
                command=self.next_step,
                bg_color="#007AFF",
                text_color="white",
                font_size=16,
                padx=50,
                pady=15
            ).pack(pady=6)

        if not ffmpeg_found:
            ModernButton(
                btn_container,
                text="Install FFmpeg",
                command=install_ffmpeg,
                bg_color="#007AFF",
                text_color="white",
                font_size=14,
                padx=30,
                pady=12
            ).pack(pady=6)
            ModernButton(
                btn_container,
                text="Open Terminal for FFmpeg",
                command=lambda: _open_terminal_install("brew install ffmpeg"),
                bg_color="#e8e8ed",
                text_color="#1d1d1f",
                font_size=12,
                padx=24,
                pady=10
            ).pack(pady=4)

        if not weasyprint_found:
            ModernButton(
                btn_container,
                text="Install WeasyPrint",
                command=install_weasyprint,
                bg_color="#007AFF",
                text_color="white",
                font_size=14,
                padx=30,
                pady=12
            ).pack(pady=6)
            ModernButton(
                btn_container,
                text="Open Terminal for WeasyPrint",
                command=lambda: _open_terminal_install("brew install pango cairo gdk-pixbuf libffi && ./venv/bin/pip install weasyprint"),
                bg_color="#e8e8ed",
                text_color="#1d1d1f",
                font_size=12,
                padx=24,
                pady=10
            ).pack(pady=4)

        if not parakeet_found:
            tk.Label(
                btn_container,
                text="(Optional: Install Parakeet-MLX for faster local transcription)",
                font=("SF Pro Display", 10),
                bg="#f5f5f7",
                fg="#86868b"
            ).pack(pady=4)
            ModernButton(
                btn_container,
                text="Open Terminal for Parakeet-MLX",
                command=lambda: _open_terminal_install("./venv/bin/pip install parakeet-mlx"),
                bg_color="#e8e8ed",
                text_color="#1d1d1f",
                font_size=11,
                padx=20,
                pady=8
            ).pack(pady=4)

        # Retry button (shown when any required dependency not found)
        if not all_required_found:
            ModernButton(
                btn_container,
                text="Re-check Dependencies",
                command=self.show_step,
                bg_color="#007AFF",
                text_color="white",
                font_size=16,
                padx=50,
                pady=15
            ).pack(pady=6)

    def setup_api_key(self):
        """Setup Anthropic API key"""
        tk.Label(
            self.main_frame,
            text="Step 2: Anthropic API Key",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=5)

        tk.Label(
            self.main_frame,
            text="Enter your Anthropic API key for Claude AI",
            font=("SF Pro Display", 12),
            bg="#f5f5f7",
            fg="#86868b"
        ).pack(pady=10)

        # API key entry
        entry_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT)
        entry_frame.pack(fill=tk.X, pady=10)

        label_frame = tk.Frame(entry_frame, bg="white")
        label_frame.pack(fill=tk.X, padx=20, pady=15)

        tk.Label(
            label_frame,
            text="API Key:",
            font=("SF Pro Display", 12, "bold"),
            bg="white"
        ).pack(side=tk.LEFT)

        tk.Label(
            label_frame,
            text="  (Paste with Cmd+V)",
            font=("SF Pro Display", 10),
            bg="white",
            fg="#86868b"
        ).pack(side=tk.LEFT)

        api_entry = tk.Entry(
            entry_frame,
            font=("SF Mono", 13),
            show="*",
            width=50,
            bg="white",
            fg="#1d1d1f",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d1d1d6",
            highlightcolor="#007AFF",
            insertbackground="#1d1d1f"
        )
        api_entry.pack(padx=20, pady=10, fill=tk.X, ipady=8)

        # Auto-focus the entry field so user can immediately paste
        api_entry.focus_set()

        # Pre-fill if exists
        from config import load_api_key
        existing_key = load_api_key()
        if existing_key:
            api_entry.insert(0, existing_key)

        # Info text
        info_text = """Don't have an API key? Get one at:
https://console.anthropic.com/"""

        tk.Label(
            self.main_frame,
            text=info_text,
            font=("SF Pro Display", 10),
            bg="#f5f5f7",
            fg="#86868b",
            justify=tk.LEFT
        ).pack(pady=15)

        # Status label
        status_label = tk.Label(
            self.main_frame,
            text="",
            font=("SF Pro Display", 11),
            bg="#f5f5f7",
            fg="#a41c27"
        )
        status_label.pack(pady=10)

        def validate_and_continue():
            """Validate API key and continue"""
            api_key = api_entry.get().strip()

            if not api_key:
                status_label.config(text="Please enter an API key")
                return

            if not api_key.startswith("sk-ant-"):
                status_label.config(text="API key should start with 'sk-ant-'")
                return

            # Save API key
            self.config['anthropic_api_key'] = api_key
            status_label.config(text="")
            self.next_step()

        # Buttons
        btn_frame = tk.Frame(self.main_frame, bg="#f5f5f7")
        btn_frame.pack(pady=20)

        ModernButton(
            btn_frame,
            text="Back",
            command=self.prev_step,
            bg_color="#e8e8ed",
            text_color="#1d1d1f",
            font_size=14,
            padx=35,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

        ModernButton(
            btn_frame,
            text="Continue",
            command=validate_and_continue,
            bg_color="#007AFF",
            text_color="white",
            font_size=14,
            padx=45,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

    def setup_openai_key(self):
        """Setup OpenAI API key (optional)"""
        tk.Label(
            self.main_frame,
            text="Step 3: OpenAI API Key (Optional)",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=5)

        tk.Label(
            self.main_frame,
            text="Enter your OpenAI API key for GPT formatting/metadata",
            font=("SF Pro Display", 12),
            bg="#f5f5f7",
            fg="#86868b"
        ).pack(pady=10)

        # API key entry
        entry_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT)
        entry_frame.pack(fill=tk.X, pady=10)

        label_frame = tk.Frame(entry_frame, bg="white")
        label_frame.pack(fill=tk.X, padx=20, pady=15)

        tk.Label(
            label_frame,
            text="API Key:",
            font=("SF Pro Display", 12, "bold"),
            bg="white"
        ).pack(side=tk.LEFT)

        tk.Label(
            label_frame,
            text="  (Paste with Cmd+V)",
            font=("SF Pro Display", 10),
            bg="white",
            fg="#86868b"
        ).pack(side=tk.LEFT)

        api_entry = tk.Entry(
            entry_frame,
            font=("SF Mono", 13),
            show="*",
            width=50,
            bg="white",
            fg="#1d1d1f",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d1d1d6",
            highlightcolor="#007AFF",
            insertbackground="#1d1d1f"
        )
        api_entry.pack(padx=20, pady=10, fill=tk.X, ipady=8)

        api_entry.focus_set()

        # Pre-fill if exists
        from config import load_openai_api_key
        existing_key = load_openai_api_key()
        if existing_key:
            api_entry.insert(0, existing_key)

        # Info text
        info_text = """Don't have an API key? Get one at:
https://platform.openai.com/"""

        tk.Label(
            self.main_frame,
            text=info_text,
            font=("SF Pro Display", 10),
            bg="#f5f5f7",
            fg="#86868b",
            justify=tk.LEFT
        ).pack(pady=15)

        # Status label
        status_label = tk.Label(
            self.main_frame,
            text="",
            font=("SF Pro Display", 11),
            bg="#f5f5f7",
            fg="#a41c27"
        )
        status_label.pack(pady=10)

        def validate_and_continue():
            """Validate OpenAI API key and continue"""
            api_key = api_entry.get().strip()

            if not api_key:
                status_label.config(text="If you don't use GPT formatting, you can skip this step.")
                return

            if not api_key.startswith("sk-"):
                status_label.config(text="OpenAI API keys typically start with 'sk-'")
                return

            self.config['openai_api_key'] = api_key
            status_label.config(text="")
            self.next_step()

        def skip_step():
            """Skip OpenAI key setup"""
            api_key = api_entry.get().strip()
            if api_key:
                # If user typed something, validate instead of skip
                validate_and_continue()
                return
            self.next_step()

        # Buttons
        btn_frame = tk.Frame(self.main_frame, bg="#f5f5f7")
        btn_frame.pack(pady=20)

        ModernButton(
            btn_frame,
            text="Back",
            command=self.prev_step,
            bg_color="#e8e8ed",
            text_color="#1d1d1f",
            font_size=14,
            padx=35,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

        ModernButton(
            btn_frame,
            text="Skip",
            command=skip_step,
            bg_color="#e8e8ed",
            text_color="#1d1d1f",
            font_size=14,
            padx=35,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

        ModernButton(
            btn_frame,
            text="Continue",
            command=validate_and_continue,
            bg_color="#007AFF",
            text_color="white",
            font_size=14,
            padx=45,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

    def setup_whisper(self):
        """Setup Whisper.cpp (optional)"""
        tk.Label(
            self.main_frame,
            text="Step 4: Whisper.cpp Setup (Optional)",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=5)

        tk.Label(
            self.main_frame,
            text="Configure Whisper.cpp if you want to use it for transcription.\nYou can also use Parakeet-MLX (local) or skip this step.",
            font=("SF Pro Display", 12),
            bg="#f5f5f7",
            fg="#86868b"
        ).pack(pady=15)

        # Mode selection
        mode_var = tk.StringVar(value="remote")

        # Remote option
        remote_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT, borderwidth=2, highlightthickness=2, highlightbackground="#007AFF")
        remote_frame.pack(fill=tk.X, pady=10)

        tk.Radiobutton(
            remote_frame,
            text="Use Remote Server",
            variable=mode_var,
            value="remote",
            font=("SF Pro Display", 14, "bold"),
            bg="white",
            fg="#1d1d1f",
            selectcolor="white",
            activebackground="white",
            padx=20,
            pady=10
        ).pack(anchor=tk.W)

        tk.Label(
            remote_frame,
            text="Connect to a Whisper.cpp server running on another machine",
            font=("SF Pro Display", 11),
            bg="white",
            fg="#86868b",
            padx=40,
            pady=5
        ).pack(anchor=tk.W)

        # Remote server fields
        remote_config = tk.Frame(remote_frame, bg="white")
        remote_config.pack(fill=tk.X, padx=40, pady=10)

        tk.Label(remote_config, text="Server Address:", bg="white", font=("SF Pro Display", 12, "bold")).grid(row=0, column=0, sticky=tk.W, pady=8)
        host_entry = tk.Entry(
            remote_config,
            font=("SF Mono", 12),
            width=30,
            bg="white",
            fg="#1d1d1f",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d1d1d6",
            highlightcolor="#007AFF",
            insertbackground="#1d1d1f"
        )
        host_entry.grid(row=0, column=1, padx=10, pady=8, ipady=5)
        host_entry.insert(0, "10.0.85.100")

        tk.Label(remote_config, text="Port:", bg="white", font=("SF Pro Display", 12, "bold")).grid(row=1, column=0, sticky=tk.W, pady=8)
        port_entry = tk.Entry(
            remote_config,
            font=("SF Mono", 12),
            width=30,
            bg="white",
            fg="#1d1d1f",
            relief=tk.FLAT,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d1d1d6",
            highlightcolor="#007AFF",
            insertbackground="#1d1d1f"
        )
        port_entry.grid(row=1, column=1, padx=10, pady=8, ipady=5)
        port_entry.insert(0, "5687")

        # Local option
        local_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT, borderwidth=2, highlightthickness=2, highlightbackground="#e8e8ed")
        local_frame.pack(fill=tk.X, pady=15)

        tk.Radiobutton(
            local_frame,
            text="Install Locally (Advanced)",
            variable=mode_var,
            value="local",
            font=("SF Pro Display", 14, "bold"),
            bg="white",
            fg="#1d1d1f",
            selectcolor="white",
            activebackground="white",
            padx=20,
            pady=10
        ).pack(anchor=tk.W)

        tk.Label(
            local_frame,
            text="Install Whisper.cpp on this machine (requires manual setup)",
            font=("SF Pro Display", 11),
            bg="white",
            fg="#86868b",
            padx=40,
            pady=10
        ).pack(anchor=tk.W)

        def save_and_continue():
            """Save Whisper config and continue"""
            mode = mode_var.get()

            if mode == "remote":
                host = host_entry.get().strip()
                port = port_entry.get().strip()

                if not host:
                    messagebox.showerror("Error", "Please enter a server address")
                    return

                try:
                    port_int = int(port)
                except ValueError:
                    messagebox.showerror("Error", "Port must be a number")
                    return

                self.config['whisper_mode'] = 'remote'
                self.config['whisper_host'] = host
                self.config['whisper_port'] = port_int
            else:
                self.config['whisper_mode'] = 'local'
                self.config['whisper_host'] = 'localhost'
                self.config['whisper_port'] = 5687
                messagebox.showinfo(
                    "Local Installation",
                    "Local Whisper.cpp installation requires manual setup.\n\n"
                    "Please install Whisper.cpp and ensure it's running on localhost:5687\n\n"
                    "See: https://github.com/ggerganov/whisper.cpp"
                )

            self.next_step()

        def skip_whisper():
            """Skip Whisper setup - use default config"""
            self.config['whisper_mode'] = 'remote'
            self.config['whisper_host'] = '10.0.85.100'
            self.config['whisper_port'] = 5687
            self.next_step()

        # Buttons
        btn_frame = tk.Frame(self.main_frame, bg="#f5f5f7")
        btn_frame.pack(pady=20)

        ModernButton(
            btn_frame,
            text="Back",
            command=self.prev_step,
            bg_color="#e8e8ed",
            text_color="#1d1d1f",
            font_size=14,
            padx=35,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

        ModernButton(
            btn_frame,
            text="Skip",
            command=skip_whisper,
            bg_color="#e8e8ed",
            text_color="#1d1d1f",
            font_size=14,
            padx=35,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

        ModernButton(
            btn_frame,
            text="Continue",
            command=save_and_continue,
            bg_color="#007AFF",
            text_color="white",
            font_size=14,
            padx=45,
            pady=12
        ).pack(side=tk.LEFT, padx=5)

    def show_complete(self):
        """Setup complete"""
        tk.Label(
            self.main_frame,
            text="Setup Complete!",
            font=("SF Pro Display", 24, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        ).pack(pady=10)

        tk.Label(
            self.main_frame,
            text="✓ Your configuration has been saved",
            font=("SF Pro Display", 14),
            bg="#f5f5f7",
            fg="#0d5c2d"
        ).pack(pady=15)

        # Summary
        summary_frame = tk.Frame(self.main_frame, bg="white", relief=tk.FLAT)
        summary_frame.pack(fill=tk.X, pady=15)

        tk.Label(
            summary_frame,
            text="Configuration Summary:",
            font=("SF Pro Display", 12, "bold"),
            bg="white",
            fg="#1d1d1f",
            padx=20,
            pady=15
        ).pack(anchor=tk.W)

        openai_tail = self.config['openai_api_key'][-8:] if self.config['openai_api_key'] else ""
        openai_display = f"{'*' * 20}{openai_tail}" if openai_tail else "Not set"

        summary_text = (
            f"Anthropic Key: {'*' * 20}{self.config['anthropic_api_key'][-8:]}\n"
            f"OpenAI Key: {openai_display}\n"
            f"Whisper Mode: {self.config['whisper_mode'].title()}"
        )

        if self.config['whisper_mode'] == 'remote':
            summary_text += f"\nWhisper Server: {self.config['whisper_host']}:{self.config['whisper_port']}"

        tk.Label(
            summary_frame,
            text=summary_text,
            font=("SF Mono", 11),
            bg="white",
            fg="#86868b",
            justify=tk.LEFT,
            padx=40,
            pady=10
        ).pack(anchor=tk.W)

        # Save config
        self.save_config()

        # Finish button
        ModernButton(
            self.main_frame,
            text="Start Using Transcript Processor",
            command=self.finish,
            bg_color="#007AFF",
            text_color="white",
            font_size=16,
            padx=50,
            pady=15
        ).pack(pady=20)

    def save_config(self):
        """Save configuration to file"""
        config_dir = Path(__file__).resolve().parent.parent / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_file = config_dir / "credentials.json"

        # Save API keys (preserve existing keys)
        existing = {}
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        existing['anthropic_api_key'] = self.config['anthropic_api_key']
        if self.config.get('openai_api_key'):
            existing['openai_api_key'] = self.config['openai_api_key']

        with open(config_file, 'w') as f:
            json.dump(existing, f, indent=2)

        # Save Whisper config
        whisper_config_file = config_dir / "whisper.json"
        with open(whisper_config_file, 'w') as f:
            json.dump({
                'mode': self.config['whisper_mode'],
                'host': self.config['whisper_host'],
                'port': self.config['whisper_port']
            }, f, indent=2)

    def finish(self):
        """Close setup wizard"""
        self.root.destroy()

    def run(self):
        """Run the setup wizard"""
        self.root.mainloop()


def needs_setup():
    """Check if first-time setup is needed"""
    # Check both project and home config locations (matches load_api_key() behavior)
    project_config = Path(__file__).resolve().parent.parent / "config" / "credentials.json"
    home_config = Path.home() / "TranscriptProcessor" / "config" / "credentials.json"

    # Config file exists in either location?
    if not (project_config.exists() or home_config.exists()):
        return True

    # WeasyPrint installed?
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return True

    return False


def run_setup():
    """Run the first-time setup wizard"""
    wizard = SetupWizard()
    wizard.run()


if __name__ == "__main__":
    run_setup()
