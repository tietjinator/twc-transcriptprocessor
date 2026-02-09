# Scoping

## Goal
Deliver a macOS application that installs and runs as a **single app bundle** with **no separate installer**. The app will include a **first‑run bootstrap** that installs required dependencies into user‑writable locations, while user data lives in standard macOS directories.

## Non‑Goals (for v1)
- Windows or Linux support
- Intel + Apple Silicon universal binary
- In‑app updater
- Automated notarization pipeline

## Constraints
- macOS 12+ target
- Apple Silicon (ARM64) only for v1
- Must not write inside the app bundle at runtime
- Avoid Homebrew dependency at install time
- First‑run bootstrap may require network access

## Key Decisions (v1)
- Use a **bootstrap installer** on first run to install runtime deps outside the app bundle
- Store runtime‑writable data in:
  - `~/Library/Application Support/Transcript Processor/`
  - `~/Library/Caches/Transcript Processor/`
  - `~/Library/Logs/Transcript Processor/`
- Prefer minimal app bundle size; install heavy deps via script

## Dependencies Strategy
- Bundle only what’s required to show the UI and run the bootstrap
- Install remaining dependencies via script into Application Support
- No Homebrew required for end users

## Distribution
- DMG for distribution
- App signed and notarized before release

## Open Questions
- Acceptable download size ceiling for the bootstrap payload
- Hosting location for dependency payloads
- Signing identity (Developer ID Application)
