# Install (macOS, Apple Silicon)

## 1) Download
Get the latest DMG from GitHub Releases:
- [Releases](https://github.com/tietjinator/twc-transcriptprocessor/releases)

## 2) Install
1. Open the DMG.
2. Drag **Transcript Processor.app** into **Applications**.
3. Eject the DMG.

## 3) First Launch
- Double‑click the app in **Applications**.
- The app will download and install its runtime on first run.
- You must be online during the first launch.

## 4) Gatekeeper (if prompted)
If macOS blocks the app:
1. Open **System Settings → Privacy & Security**.
2. Find the app warning and click **Open Anyway**.
3. Re‑launch the app.

## Logs
Bootstrap log:
- `~/Library/Logs/Transcript Processor/bootstrap.log`

## Uninstall
1. Delete **Transcript Processor.app** from Applications.
2. Remove runtime data:
   - `~/Library/Application Support/Transcript Processor`
   - `~/Library/Logs/Transcript Processor`
