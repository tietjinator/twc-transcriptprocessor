# Requirements

## Functional
- App installs as a single `.app` bundle.
- No separate installer required; app performs a **first‑run bootstrap** for dependencies.
- App launches via double‑click and displays the UI.
- Supports transcription (Parakeet/Whisper) and PDF output.
- Allows entering and storing API keys.

## Platform
- macOS 12+ only
- Apple Silicon (ARM64) only for v1

## Runtime Storage
- Config and credentials stored outside the app bundle.
- Temp and cache files stored outside the app bundle.

## Dependencies
- Minimal runtime bundled inside app for UI + bootstrap.
- Remaining deps installed by script into Application Support.
- No Homebrew requirement for end users.
- Network required on first run (unless a local payload is provided).

## Security & Privacy
- Avoid storing API keys inside the app bundle.
- Clear location for credentials; protect with OS permissions.

## Usability
- One‑step install (drag‑and‑drop into /Applications is ideal).
- Provide clear progress + error messages during bootstrap.
- Provide retry if dependency install fails.

## Distribution
- Prefer signed and notarized app.
- Provide DMG distribution.

## Performance
- Startup under 5 seconds on modern Macs after bootstrap completes.
- Local transcription should not block the UI.
