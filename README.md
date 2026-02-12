# Transcript Processor (Bootstrap + Runtime Installer)

This repository builds a **macOS bootstrap app** that downloads and installs the full Transcript Processor runtime on first launch. The goal is a simple, double‑click install experience for Apple Silicon Macs.

## Quick Install
- Download the DMG from [GitHub Releases](https://github.com/tietjinator/twc-transcriptprocessor/releases)
- Drag **Transcript Processor.app** into **Applications**
- Launch the app and let it install the runtime on first run

Full install guide: `INSTALL.md`

## What This Repo Contains
- A lightweight `.app` bundle that shows a setup UI and installs a runtime.
- The runtime app source in `src/` and assets in `assets/`, versioned in this repository.
- A runtime payload build script that packages a portable Python runtime + app code.
- Scripts to build the app and publish the payload to GitHub Releases.

## Supported Platform
- macOS 12+ (Apple Silicon / ARM64 only for v0.1.x)

## How It Works
1. User double‑clicks the app.
2. On every launch, the bootstrap app checks `runtime_manifest.json` for runtime updates.
3. If a newer runtime is available, it downloads `runtime_payload.tar.gz`, verifies SHA‑256 integrity, installs, and relaunches.
4. If offline and a valid runtime is already installed, it launches using the installed runtime.
5. The runtime is extracted into:
   `~/Library/Application Support/Transcript Processor/runtime`
6. Dependencies are installed in a venv.
7. The real app launches automatically.

## Build (Local)
### Build the runtime payload
```bash
bash "./scripts/build_runtime_payload.sh"
```
The script uses this repository's `src/` and `requirements.txt` by default.
You can override with `TPP_APP_SRC_ROOT` and `TPP_REQUIREMENTS` if needed.

### Build the macOS app
```bash
bash "./scripts/build_macos.sh"
```

Output:
- App bundle: `build/dist/Transcript Processor.app`
- Payload: `build/runtime_payload.tar.gz`
- Payload hash file: `build/runtime_payload.sha256`

### Build runtime manifest
```bash
bash "./scripts/build_runtime_manifest.sh"
```

Output:
- Manifest: `build/runtime_manifest.json`

## Publish Release Assets
```bash
gh release upload v0.1.0 \
  "./build/runtime_payload.tar.gz" \
  "./build/runtime_manifest.json" \
  "./build/Transcript_Processor.dmg" \
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
- Runtime manifest URL is controlled by `TPP_RUNTIME_MANIFEST_URL`.
- Payload URL fallback is controlled by `TPP_RUNTIME_URL`.
- The bootstrap log lives at:
  `~/Library/Logs/Transcript Processor/bootstrap.log`
- Startup update check log (surfaced in Activity Log):
  `~/Library/Application Support/Transcript Processor/startup_update_log.jsonl`

## Security
- API keys are **not** stored in the app bundle.
- Credentials are stored in user‑level config files at runtime.

---

For more detail, see:
- `docs/REQUIREMENTS.md`
- `docs/PIPELINE.md`
