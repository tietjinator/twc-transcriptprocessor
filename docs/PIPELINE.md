# Build & Packaging Pipeline (Draft)

## Overview
Goal: produce a `.app` bundle that can **bootstrap its dependencies** on first run, avoiding a large bundled runtime where possible.

## Candidate Approaches
1. PyInstaller
2. Briefcase (BeeWare)
3. py2app

## Selected Tool (v1)
**PyInstaller** — flexible for bundling a minimal runtime + bootstrap UI while keeping heavy deps out of the app.

### Why
- Handles complex dependency graphs better than py2app for mixed native libs.
- Widely used for macOS app bundling with Python.
- Lets us control embedded assets and bootstrap behavior.

### Known Risks
- WeasyPrint native deps and Parakeet assets must be fetched and wired correctly.
- Bootstrap flow must be resilient to partial installs or network failure.

## Proposed Steps (Bootstrap path)
1. Build a **minimal app** with PyInstaller:
   - UI entrypoint
   - Bootstrap installer module
2. On first launch, bootstrap downloads or unpacks a **dependency payload** into:
   - `~/Library/Application Support/Transcript Processor/runtime/`
3. App configures `PYTHONPATH` / dynamic library paths to use the installed runtime.
4. Subsequent launches skip bootstrap if runtime is present.
5. Sign + notarize.

## Artifacts
- `dist/Transcript Processor.app`
- `dist/Transcript Processor.dmg`
- Optional: `runtime_payload.zip` (hosted or shipped alongside DMG)

## Script Skeleton
- `scripts/build_macos.sh`
- `scripts/pyinstaller.spec`
- `scripts/build_runtime_payload.sh` (to be added)

## Work Items
- Define exact dependency list to install via bootstrap.
- Decide on payload hosting (local DMG vs CDN).
- Identify all dynamic libs required by WeasyPrint.
- Verify Parakeet model packaging strategy.
- Add first‑run migration for existing users.
