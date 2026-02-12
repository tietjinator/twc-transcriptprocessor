#!/usr/bin/env python3
"""
Transcript Processor - Modern macOS Application
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from pathlib import Path
import threading
import queue
import json
import os
import re
from PIL import Image, ImageTk
from config import load_api_key, HOME_CONFIG_FILE
# from first_time_setup import needs_setup, run_setup  # Disabled - skip setup wizard


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


class TranscriptProcessorApp:
    """Modern macOS-style application for transcript processing"""

    def __init__(self):
        runtime_root = Path(__file__).resolve().parents[2]
        self.startup_update_log_path = runtime_root.parent / "startup_update_log.jsonl"
        model_cache = runtime_root / "models" / "huggingface"
        model_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(model_cache))
        os.environ.setdefault("HF_HOME", str(model_cache))

        # Skip first-time setup - launch directly
        # if needs_setup():
        #     run_setup()
        #     # After setup, verify it completed successfully
        #     if needs_setup():
        #         # User cancelled setup - exit
        #         return

        self.root = tk.Tk()
        self.root.title("🎤 Transcript Processor PDF")
        self.root.geometry("900x660")
        self.root.resizable(True, True)

        self.main_thread_id = threading.get_ident()
        self.log_queue = queue.Queue()

        # Set minimum size
        self.root.minsize(850, 620)

        # Track collapsed/expanded window heights
        self.collapsed_height = 660
        self.expanded_height = 1110

        # Set background color
        self.root.configure(bg="#f5f5f7")

        # Get API key from config file
        self.api_key = load_api_key()
        if not self.api_key:
            saved = self.prompt_for_api_keys()
            if saved:
                self.api_key = saved.get("anthropic_api_key")
            if not self.api_key:
                # API key not found - prompt for it or check environment
                messagebox.showerror(
                    "Configuration Error",
                    "Anthropic API key not found.\n\n"
                    "Please set your API key in one of these locations:\n"
                    "1. config/credentials.json file with key 'anthropic_api_key'\n"
                    "2. ~/TranscriptProcessor/config/credentials.json\n"
                    "3. Environment variable ANTHROPIC_API_KEY\n\n"
                    "Or run: python3 src/save_api_key.py"
                )
                self.root.destroy()
                return

        # Initialize processor (import after setup so missing deps don't crash launch)
        try:
            from transcript_processor import TranscriptProcessor
            self.processor = TranscriptProcessor(self.api_key)
        except Exception as e:
            messagebox.showerror("Initialization Error", str(e))
            self.root.destroy()
            return

        self.setup_ui()
        self.log("Runtime build: 0.1.6")
        self.load_startup_update_log()
        self.check_services_on_startup()
        # Start periodic log flushing on the UI thread.
        self.root.after(100, self._flush_log_queue)

    def load_startup_update_log(self):
        """Read startup update events produced by bootstrap and append to activity log."""
        path = self.startup_update_log_path
        if not path.exists():
            return

        messages = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                        msg = str(payload.get("message", "")).strip()
                    except Exception:
                        msg = line
                    if msg:
                        messages.append(msg)
        except Exception as exc:
            messages = [f"Update Check: could not read startup update log ({exc})"]
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        if messages:
            self.log("Update Check:")
            for msg in messages:
                self.log(f"  {msg}")
            self.log("")

    def _save_api_keys(self, anthropic_key: str, openai_key: str | None) -> Path:
        config = {}
        if HOME_CONFIG_FILE.exists():
            try:
                with open(HOME_CONFIG_FILE, "r") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        config["anthropic_api_key"] = anthropic_key
        if openai_key:
            config["openai_api_key"] = openai_key

        HOME_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HOME_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        try:
            HOME_CONFIG_FILE.chmod(0o600)
        except Exception:
            pass
        return HOME_CONFIG_FILE

    def prompt_for_api_keys(self):
        """Prompt user for API keys and save to config"""
        dialog = tk.Toplevel(self.root)
        dialog.title("API Keys Required")
        dialog.geometry("520x300")
        dialog.configure(bg="#f5f5f7")
        dialog.transient(self.root)
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

        saved = {}

        def on_save():
            anthropic_key = anthropic_entry.get().strip()
            openai_key = openai_entry.get().strip()

            if not anthropic_key:
                messagebox.showerror("API Key Required", "Anthropic API key is required.", parent=dialog)
                return

            if not anthropic_key.startswith("sk-ant-"):
                proceed = messagebox.askyesno(
                    "Confirm Key",
                    "Anthropic key does not start with 'sk-ant-'. Continue anyway?",
                    parent=dialog
                )
                if not proceed:
                    return

            if openai_key and not openai_key.startswith("sk-"):
                proceed = messagebox.askyesno(
                    "Confirm Key",
                    "OpenAI key does not start with 'sk-'. Continue anyway?",
                    parent=dialog
                )
                if not proceed:
                    return

            self._save_api_keys(anthropic_key, openai_key or None)
            saved["anthropic_api_key"] = anthropic_key
            if openai_key:
                saved["openai_api_key"] = openai_key
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
        return saved or None

    def setup_ui(self):
        """Setup the modern user interface"""

        # Main container
        main_container = tk.Frame(self.root, bg="#f5f5f7")
        main_container.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)

        # Header
        header_frame = tk.Frame(main_container, bg="#f5f5f7")
        header_frame.pack(fill=tk.X, pady=(0, 20))

        # Load and display reel-to-reel image
        try:
            image_path = Path(__file__).resolve().parent.parent / "assets" / "Teac-A-3300SX-Reel-to-Reel-Tape-Deck-Recorder-Player-Reel-to-Reel-Tape-Players-Recorders_2048x2048 Medium.png"
            reel_image = Image.open(image_path)
            # Resize to fit nicely in header (80x80)
            reel_image = reel_image.resize((80, 80), Image.Resampling.LANCZOS)
            self.reel_photo = ImageTk.PhotoImage(reel_image)

            image_label = tk.Label(
                header_frame,
                image=self.reel_photo,
                bg="#f5f5f7"
            )
            image_label.pack(pady=(0, 10))
        except Exception as e:
            # Fallback to text if image can't be loaded
            print(f"Could not load image: {e}")

        title_label = tk.Label(
            header_frame,
            text="Transcript Processor PDF",
            font=("SF Pro Display", 28, "bold"),
            bg="#f5f5f7",
            fg="#1d1d1f"
        )
        title_label.pack()

        # File selection card
        card_frame = tk.Frame(
            main_container,
            bg="white",
            relief=tk.FLAT,
            borderwidth=0
        )
        card_frame.pack(fill=tk.X, pady=(0, 20))

        # Add subtle shadow effect with frame layering
        shadow_frame = tk.Frame(main_container, bg="#e5e5e5", height=2)
        shadow_frame.place(in_=card_frame, relx=0, rely=1, relwidth=1)

        card_inner = tk.Frame(card_frame, bg="white")
        card_inner.pack(fill=tk.BOTH, padx=30, pady=24)

        info_label = tk.Label(
            card_inner,
            text="Select Files to Process",
            font=("SF Pro Display", 18, "bold"),
            bg="white",
            fg="#1d1d1f"
        )
        info_label.pack(pady=(0, 10))

        supported_label = tk.Label(
            card_inner,
            text="Supported: MP3, MP4, WAV, M4A, MOV, and more",
            font=("SF Pro Display", 11),
            bg="white",
            fg="#86868b"
        )
        supported_label.pack(pady=(0, 22))

        # Modern buttons
        button_frame = tk.Frame(card_inner, bg="white")
        button_frame.pack()

        # Select Files button (bright blue)
        files_btn = ModernButton(
            button_frame,
            text="🎵  Select Files",
            command=self.browse_files,
            bg_color="#007AFF",
            text_color="white",
            font_size=15,
            padx=35,
            pady=12
        )
        files_btn.pack(side=tk.LEFT, padx=8)

        # Select Folder button (darker blue)
        folder_btn = ModernButton(
            button_frame,
            text="📁  Select Folder",
            command=self.browse_folder,
            bg_color="#0051D5",
            text_color="white",
            font_size=15,
            padx=35,
            pady=12
        )
        folder_btn.pack(side=tk.LEFT, padx=8)

        self.include_subfolders = tk.BooleanVar(value=False)
        scan_toggle = tk.Checkbutton(
            card_inner,
            text="Include subfolders when using Select Folder",
            variable=self.include_subfolders,
            bg="white",
            fg="#1d1d1f",
            activebackground="white",
            activeforeground="#1d1d1f",
            selectcolor="white",
            font=("SF Pro Display", 11),
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )
        scan_toggle.pack(pady=(14, 2))

        # Processing options (compact grid layout)
        options_frame = tk.Frame(card_inner, bg="white")
        options_frame.pack(pady=(16, 0))

        # Column 1: Transcription engine
        transcription_container = tk.Frame(options_frame, bg="white")
        transcription_container.grid(row=0, column=0, padx=15)

        tk.Label(
            transcription_container,
            text="Transcription:",
            font=("SF Pro Display", 11, "bold"),
            bg="white",
            fg="#1d1d1f"
        ).pack(anchor=tk.W)

        self.transcription_engine = tk.StringVar(value="🚀 Parakeet-MLX (Local)")
        transcription_dropdown = tk.OptionMenu(
            transcription_container,
            self.transcription_engine,
            "🚀 Parakeet-MLX (Local)",
            "☁️ Whisper.cpp (Manual Setup)"
        )
        transcription_dropdown.config(
            font=("SF Pro Display", 10),
            bg="white",
            fg="#1d1d1f",
            highlightthickness=0,
            relief=tk.FLAT,
            cursor="hand2",
            width=20
        )
        transcription_dropdown.pack(anchor=tk.W, pady=(5, 0))

        # Column 2: Paragraph formatting
        formatting_container = tk.Frame(options_frame, bg="white")
        formatting_container.grid(row=0, column=1, padx=15)

        tk.Label(
            formatting_container,
            text="Formatting:",
            font=("SF Pro Display", 11, "bold"),
            bg="white",
            fg="#1d1d1f"
        ).pack(anchor=tk.W)

        self.formatting_engine = tk.StringVar(value="⚡ GPT-4o mini")
        formatting_dropdown = tk.OptionMenu(
            formatting_container,
            self.formatting_engine,
            "🚀 GPT-5 nano",
            "⚡ GPT-4o mini",
            "☁️ Claude Haiku 3.5"
        )
        formatting_dropdown.config(
            font=("SF Pro Display", 10),
            bg="white",
            fg="#1d1d1f",
            highlightthickness=0,
            relief=tk.FLAT,
            cursor="hand2",
            width=20
        )
        formatting_dropdown.pack(anchor=tk.W, pady=(5, 0))

        # Column 3: Metadata extraction
        metadata_container = tk.Frame(options_frame, bg="white")
        metadata_container.grid(row=0, column=2, padx=15)

        tk.Label(
            metadata_container,
            text="Metadata:",
            font=("SF Pro Display", 11, "bold"),
            bg="white",
            fg="#1d1d1f"
        ).pack(anchor=tk.W)

        self.metadata_engine = tk.StringVar(value="☁️ Claude Haiku 4.5")
        metadata_dropdown = tk.OptionMenu(
            metadata_container,
            self.metadata_engine,
            "🚀 GPT-5 nano",
            "⚡ GPT-4o mini",
            "☁️ Claude Haiku 3.5",
            "☁️ Claude Haiku 4.5"
        )
        metadata_dropdown.config(
            font=("SF Pro Display", 10),
            bg="white",
            fg="#1d1d1f",
            highlightthickness=0,
            relief=tk.FLAT,
            cursor="hand2",
            width=20
        )
        metadata_dropdown.pack(anchor=tk.W, pady=(5, 0))

        # Status bar (appears right after file selection)
        status_container = tk.Frame(main_container, bg="#f5f5f7")
        status_container.pack(fill=tk.X, pady=(12, 8))  # Keep activity log visible in collapsed layout

        self.status_label = tk.Label(
            status_container,
            text="Ready",
            font=("SF Pro Display", 11),
            bg="#e8e8ed",
            fg="#1d1d1f",
            anchor=tk.W,
            padx=20,
            pady=12
        )
        self.status_label.pack(fill=tk.X)

        # Progress Log section (collapsible)
        log_container = tk.Frame(main_container, bg="#f5f5f7")
        log_container.pack(fill=tk.X, pady=0)  # No extra padding

        # Log header with toggle button
        log_header_frame = tk.Frame(log_container, bg="#f5f5f7")
        log_header_frame.pack(fill=tk.X)

        self.log_expanded = False  # Start collapsed

        # Use ModernButton for consistent styling
        self.log_toggle_btn = ModernButton(
            log_header_frame,
            text="▶  Activity Log",  # Start with collapsed arrow
            command=self.toggle_log,
            bg_color="#E8F0FE",  # Very light blue
            text_color="#1d1d1f",
            font_size=13,
            padx=20,
            pady=8
        )
        self.log_toggle_btn.pack(side=tk.LEFT)

        # Collapsible log content (start hidden since log_expanded = False)
        self.log_content = tk.Frame(log_container, bg="#f5f5f7")
        # Don't pack initially - will be packed when user clicks to expand

        # Log text card with modern styling
        log_card = tk.Frame(
            self.log_content,
            bg="white",
            relief=tk.FLAT,
            borderwidth=0
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        # Shadow effect
        shadow_frame = tk.Frame(log_container, bg="#e5e5e5", height=2)
        shadow_frame.place(in_=log_card, relx=0, rely=1, relwidth=1)

        self.log_text = scrolledtext.ScrolledText(
            log_card,
            font=("SF Mono", 11),
            bg="white",
            fg="#1d1d1f",
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=12,
            padx=12,
            pady=12,
            height=15  # Taller by default
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Animation variables
        self.activity_animation_running = False
        self.activity_dots = 0
        self.processing_active = False
        self.ready_reset_after_id = None
        self.idle_status = ("Ready", "#e8e8ed", "#1d1d1f")

    def _set_status(self, text: str, bg: str, fg: str):
        self.status_label.config(text=text, bg=bg, fg=fg)

    def _cancel_idle_reset(self):
        if self.ready_reset_after_id:
            self.root.after_cancel(self.ready_reset_after_id)
            self.ready_reset_after_id = None

    def _restore_idle_status(self):
        self.ready_reset_after_id = None
        self._set_status(*self.idle_status)

    def _schedule_idle_reset(self, delay_ms: int = 2500):
        self._cancel_idle_reset()
        self.ready_reset_after_id = self.root.after(delay_ms, self._restore_idle_status)

    def check_services_on_startup(self):
        """Check service availability when app starts"""
        self.log("Checking services...")

        status = self.processor.check_services()

        # Required services
        self.log("\nRequired Services:")
        if status["claude"]:
            self.log("  ✓ Claude API key valid")
        else:
            self.log("  ✗ Claude API key invalid")

        if status["ffmpeg"]:
            self.log("  ✓ FFmpeg available")
        else:
            self.log("  ✗ FFmpeg not found")

        if status["weasyprint"]:
            self.log("  ✓ WeasyPrint available (PDF generation)")
        else:
            self.log("  ✗ WeasyPrint not found (PDF generation will fail)")

        # Optional services
        self.log("\nOptional Services:")
        if status["openai"]:
            self.log("  ✓ OpenAI API key valid (GPT models available)")
        else:
            self.log("  ○ OpenAI API not configured (GPT models unavailable)")

        # Transcription engines
        self.log("\nTranscription Engines:")
        if status["parakeet"]:
            self.log("  ✓ Parakeet-MLX available (local, recommended)")
        else:
            self.log("  ○ Parakeet-MLX not installed (recommended)")

        if status["whisper"]:
            self.log("  ✓ Whisper.cpp service connected (optional)")
        else:
            self.log("  ○ Whisper.cpp not configured (optional, requires manual setup)")

        # Additional messages
        if status["messages"]:
            self.log("\nNotes:")
            for msg in status["messages"]:
                self.log(f"  • {msg}")

        # Determine if core requirements are met
        required_ready = status["claude"] and status["ffmpeg"] and status["weasyprint"]
        transcription_ready = status["whisper"] or status["parakeet"]

        if required_ready and transcription_ready:
            self.log("\n✓ All systems ready!")
            self.idle_status = ("✓ Ready to process files", "#d1f4e0", "#0d5c2d")
            self._set_status(*self.idle_status)
        elif required_ready:
            self.log("\n⚠️ Core services ready, but no transcription engine available.")
            self.idle_status = ("⚠️ Check transcription settings", "#fff4ce", "#805800")
            self._set_status(*self.idle_status)
        else:
            self.log("\n✗ Required services missing. Please resolve issues above.")
            self.idle_status = ("✗ Not ready - check log", "#ffe0e0", "#a41c27")
            self._set_status(*self.idle_status)

    def browse_files(self):
        """Browse for individual files"""
        filetypes = [
            ("Audio Files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),
            ("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"),
            ("All Files", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Select Media Files",
            filetypes=filetypes
        )

        if files:
            file_paths = [Path(f) for f in files]
            self.process_files(file_paths)

    def browse_folder(self):
        """Browse for a folder and process all media files in it"""
        folder = filedialog.askdirectory(
            title="Select Folder Containing Media Files"
        )

        if folder:
            folder_path = Path(folder)
            recursive = bool(self.include_subfolders.get())
            from config import SUPPORTED_EXTENSIONS
            media_files = []
            for ext in SUPPORTED_EXTENSIONS:
                if recursive:
                    media_files.extend(folder_path.rglob(f"*{ext}"))
                else:
                    media_files.extend(folder_path.glob(f"*{ext}"))

            # De-duplicate while preserving deterministic order.
            unique_files = []
            seen = set()
            for file_path in sorted(media_files, key=lambda p: str(p).lower()):
                if not file_path.is_file():
                    continue
                key = str(file_path)
                if key in seen:
                    continue
                seen.add(key)
                unique_files.append(file_path)

            if not unique_files:
                scope = "this folder and its subfolders" if recursive else "this folder"
                messagebox.showinfo("No Files Found", f"No supported media files found in {scope}.")
                return

            scope = "including subfolders" if recursive else "top-level only"
            self.log(f"\nFound {len(unique_files)} media files in folder ({scope})")
            self.process_files(unique_files)

    def process_files(self, file_paths):
        """Process files in background thread"""
        self.log(f"\n{'='*60}")
        self.log(f"Starting processing of {len(file_paths)} file(s)...")
        self.log(f"{'='*60}\n")

        # Log selected engines
        self.log(f"Transcription: {self.transcription_engine.get()}")
        self.log(f"Formatting: {self.formatting_engine.get()}")
        self.log(f"Metadata: {self.metadata_engine.get()}\n")

        self._cancel_idle_reset()
        self.processing_active = True
        self._set_status(f"⏳ Processing {len(file_paths)} files", "#fff4ce", "#805800")

        # Start activity indicator (adds animated dots to status)
        self.start_activity_indicator()

        # Run in background thread
        thread = threading.Thread(
            target=self._process_files_thread,
            args=(file_paths,),
            daemon=True
        )
        thread.start()

    def _process_files_thread(self, file_paths):
        """Background thread for processing files"""
        try:
            # Configure processor based on dropdown selections
            from config import TRANSCRIPTION_ENGINE_PARAKEET, TRANSCRIPTION_ENGINE_WHISPER

            # Map transcription engine dropdown to config constant
            if self.transcription_engine.get() == "🚀 Parakeet-MLX (Local)":
                self.processor.transcription_engine = TRANSCRIPTION_ENGINE_PARAKEET
            else:
                self.processor.transcription_engine = TRANSCRIPTION_ENGINE_WHISPER

            # Map formatting engine dropdown to model name
            formatting_choice = self.formatting_engine.get()
            if formatting_choice == "🚀 GPT-5 nano":
                self.processor.openai_formatting_model = "gpt-5-nano"
            elif formatting_choice == "⚡ GPT-4o mini":
                self.processor.openai_formatting_model = "gpt-4o-mini"
            else:  # Claude Haiku 3.5
                self.processor.openai_formatting_model = None

            # Map metadata engine dropdown to model name
            metadata_choice = self.metadata_engine.get()
            if metadata_choice == "🚀 GPT-5 nano":
                self.processor.openai_metadata_model = "gpt-5-nano"
            elif metadata_choice == "⚡ GPT-4o mini":
                self.processor.openai_metadata_model = "gpt-4o-mini"
            else:  # Claude Haiku 4.5
                self.processor.openai_metadata_model = None

            results = self.processor.process_files_pipelined(
                file_paths,
                progress_callback=self.log
            )

            # Tk is not thread-safe; queue control events for the main thread.
            self.log_queue.put(("__PROCESS_COMPLETE__", len(results), len(file_paths)))

        except Exception as e:
            self.log_queue.put(("__PROCESS_ERROR__", str(e)))

    def _processing_complete(self, success_count, total_count):
        """Called when processing completes"""
        # Stop activity indicator
        self.stop_activity_indicator()
        self.processing_active = False

        if success_count == total_count:
            self._set_status(f"✓ Completed: {success_count} files processed successfully", "#d1f4e0", "#0d5c2d")
            self.log(f"\n✓ All files processed successfully!")
            self._schedule_idle_reset(2200)
        else:
            self._set_status(f"⚠️  Completed: {success_count}/{total_count} files processed", "#fff4ce", "#805800")
            self.log(f"\n⚠️  {success_count} of {total_count} files processed")
            self._schedule_idle_reset(3500)

    def _processing_error(self, error_msg):
        """Called when processing fails"""
        # Stop activity indicator
        self.stop_activity_indicator()
        self.processing_active = False
        self._cancel_idle_reset()
        self._set_status("✗ Processing failed", "#ffdce0", "#a41c27")
        self.log(f"\n✗ Error: {error_msg}")
        messagebox.showerror("Processing Error", error_msg)

    def toggle_log(self):
        """Toggle log visibility and window size"""
        if self.log_expanded:
            # Collapse
            self.log_content.pack_forget()
            self.log_toggle_btn.itemconfig(self.log_toggle_btn.text_id, text="▶  Activity Log")
            self.log_expanded = False

            # Shrink window back to collapsed height
            current_width = self.root.winfo_width()
            self.root.geometry(f"{current_width}x{self.collapsed_height}")
        else:
            # Expand
            self.log_content.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
            self.log_toggle_btn.itemconfig(self.log_toggle_btn.text_id, text="▼  Activity Log")
            self.log_expanded = True

            # Expand window to show full log
            current_width = self.root.winfo_width()
            self.root.geometry(f"{current_width}x{self.expanded_height}")

    def start_activity_indicator(self):
        """Start animated activity indicator in status bar"""
        self.activity_animation_running = True
        self.base_status_text = self.status_label.cget("text")  # Save base text
        self._animate_activity()

    def stop_activity_indicator(self):
        """Stop activity indicator"""
        self.activity_animation_running = False

    def _maybe_finalize_from_log(self, message: str):
        """Fallback status reset when completion is reported through streamed logs."""
        if not self.processing_active:
            return
        match = re.search(
            r"completed:\s*(\d+)\s*/\s*(\d+)\s*files processed successfully",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            success_count = int(match.group(1))
            total_count = int(match.group(2))
        else:
            fallback = re.search(
                r"successful:\s*(\d+)\s*/\s*(\d+)",
                message,
                flags=re.IGNORECASE,
            )
            if not fallback:
                return
            success_count = int(fallback.group(1))
            total_count = int(fallback.group(2))

        self.stop_activity_indicator()
        self.processing_active = False

        if success_count == total_count:
            self._set_status(f"✓ Completed: {success_count} files processed successfully", "#d1f4e0", "#0d5c2d")
            self._schedule_idle_reset(2200)
        else:
            self._set_status(f"⚠️  Completed: {success_count}/{total_count} files processed", "#fff4ce", "#805800")
            self._schedule_idle_reset(3500)

    def _animate_activity(self):
        """Animate dots in status bar"""
        if not self.activity_animation_running:
            return

        # Add animated dots to the status text
        dots = "." * (self.activity_dots % 4)
        self.status_label.config(text=f"{self.base_status_text}{dots}")
        self.activity_dots += 1

        # Continue animation
        self.root.after(500, self._animate_activity)

    def log(self, message):
        """Add message to log"""
        if threading.get_ident() != self.main_thread_id:
            self.log_queue.put(message)
            return
        self._append_log(message)

    def _append_log(self, message: str):
        text = str(message)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self._maybe_finalize_from_log(text)
        self.root.update_idletasks()

    def _flush_log_queue(self):
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(msg, tuple) and msg:
                event = msg[0]
                if event == "__PROCESS_COMPLETE__":
                    self._processing_complete(msg[1], msg[2])
                    continue
                if event == "__PROCESS_ERROR__":
                    self._processing_error(msg[1])
                    continue
            self._append_log(msg)
        self.root.after(100, self._flush_log_queue)

    def run(self):
        """Run the application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    app = TranscriptProcessorApp()
    app.run()


if __name__ == "__main__":
    main()
