# Transcript Processor (Bootstrap + Runtime Installer)

This repository builds a **macOS bootstrap app** that downloads and installs the full Transcript Processor runtime on first launch. The goal is a simple, double‑click install experience for Apple Silicon Macs.

## Quick Install
- Download the DMG from [GitHub Releases](https://github.com/tietjinator/twc-transcriptprocessor/releases)
- Drag **Transcript Processor.app** into **Applications**
- Launch the app and let it install the runtime on first run

Full install guide: `/Users/matthewtietje/TWC Archives Transcript Processor app/INSTALL.md`

## What This Repo Contains
- A lightweight `.app` bundle that shows a setup UI and installs a runtime.
- A runtime payload build script that packages a portable Python runtime + app code.
- Scripts to build the app and publish the payload to GitHub Releases.

## Supported Platform
- macOS 12+ (Apple Silicon / ARM64 only for v0.1.x)

## How It Works
1. User double‑clicks the app.
2. The bootstrap UI downloads `runtime_payload.tar.gz` from GitHub Releases.
3. The runtime is extracted into:
   `~/Library/Application Support/Transcript Processor/runtime`
4. Dependencies are installed in a venv.
5. The real app launches automatically.

## Build (Local)
### Build the runtime payload
```bash
bash "/Users/matthewtietje/TWC Archives Transcript Processor app/scripts/build_runtime_payload.sh"
```

### Build the macOS app
```bash
bash "/Users/matthewtietje/TWC Archives Transcript Processor app/scripts/build_macos.sh"
```

Output:
- App bundle: `/Users/matthewtietje/TWC Archives Transcript Processor app/build/dist/Transcript Processor.app`
- Payload: `/Users/matthewtietje/TWC Archives Transcript Processor app/build/runtime_payload.tar.gz`

## Publish Payload
```bash
gh release upload v0.1.0 \
  "/Users/matthewtietje/TWC Archives Transcript Processor app/build/runtime_payload.tar.gz" \
  --repo tietjinator/twc-transcriptprocessor --clobber
```

## Dependencies (and Credits)
This project depends on the following excellent open‑source projects and services:

### Runtime / Build
- [python-build-standalone](https://github.com/indygreg/python-build-standalone) — portable Python runtime used in the payload.
- [PyInstaller](https://pyinstaller.org/) — builds the bootstrap macOS app.
- [Tcl/Tk](https://www.tcl.tk/) — UI toolkit for the bootstrap app.

### Media + Document Pipeline
- [FFmpeg](https://ffmpeg.org/) — audio/video processing.
- [WeasyPrint](https://weasyprint.org/) — HTML → PDF rendering.
- [Pango](https://pango.gnome.org/), [Cairo](https://www.cairographics.org/), [GDK-Pixbuf](https://developer.gnome.org/gdk-pixbuf/), [libffi](https://sourceware.org/libffi/) — system libraries required by WeasyPrint.

### AI / Transcription
- [Parakeet‑MLX](https://github.com/argmaxinc/parakeet) — optional local transcription engine.
- [OpenAI API](https://platform.openai.com/) — optional formatting / LLM services.
- [Anthropic API](https://www.anthropic.com/) — Claude formatting / LLM services.

All trademarks and licenses remain with their respective owners. This project is not affiliated with these providers.

## Notes
- Runtime downloads are controlled by `TPP_RUNTIME_URL` in `app/runtime.py`.
- The bootstrap log lives at:
  `~/Library/Logs/Transcript Processor/bootstrap.log`

## Security
- API keys are **not** stored in the app bundle.
- Credentials are stored in user‑level config files at runtime.

---

For more detail, see:
- `/Users/matthewtietje/TWC Archives Transcript Processor app/docs/REQUIREMENTS.md`
- `/Users/matthewtietje/TWC Archives Transcript Processor app/docs/PIPELINE.md`
