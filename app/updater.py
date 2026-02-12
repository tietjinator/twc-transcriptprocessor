from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from app.bootstrap import (
        _chmod_runtime_bin,
        _clear_quarantine,
        _download_with_progress,
        _ensure_system_deps,
        _extract_tar,
        _install_runtime,
        _resolve_ca_bundle,
        log as bootstrap_log,
    )
    from app.runtime import (
        APP_SUPPORT_DIR,
        MODEL_CACHE_DIR,
        RUNTIME_DIR,
        installed_runtime_version,
        is_remote_newer,
        runtime_installed,
        runtime_manifest_url,
    )
except Exception:
    from bootstrap import (  # type: ignore
        _chmod_runtime_bin,
        _clear_quarantine,
        _download_with_progress,
        _ensure_system_deps,
        _extract_tar,
        _install_runtime,
        _resolve_ca_bundle,
        log as bootstrap_log,
    )
    from runtime import (  # type: ignore
        APP_SUPPORT_DIR,
        MODEL_CACHE_DIR,
        RUNTIME_DIR,
        installed_runtime_version,
        is_remote_newer,
        runtime_installed,
        runtime_manifest_url,
    )


UPDATE_STATE_FILE = APP_SUPPORT_DIR / "update_state.json"
STARTUP_UPDATE_LOG = APP_SUPPORT_DIR / "startup_update_log.jsonl"
UPDATE_PAYLOAD_FILE = APP_SUPPORT_DIR / "runtime_payload_update.tar.gz"


class UpdateError(RuntimeError):
    pass


class NetworkError(UpdateError):
    pass


class ManifestError(UpdateError):
    pass


class IntegrityError(UpdateError):
    pass


@dataclass
class UpdateDecision:
    action: str
    messages: list[str]
    error: str | None = None
    manifest: dict | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_local_runtime_version() -> str:
    version = installed_runtime_version()
    return version or "unknown"


def _normalize_compare_version(version: str) -> str:
    if not version or version == "unknown":
        return "0.0.0"
    try:
        # Validate against strict dotted-number parsing.
        is_remote_newer("0.0.0", version)
        return version
    except Exception:
        return "0.0.0"


def _write_startup_update_log(messages: list[str]) -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STARTUP_UPDATE_LOG, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps({"ts": _now_iso(), "message": msg}) + "\n")


def _write_update_state(state: dict) -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def fetch_manifest(timeout_s: int = 3) -> dict:
    url = runtime_manifest_url()
    req = urllib.request.Request(url, headers={"User-Agent": "TranscriptProcessorUpdater/1.0"})
    cafile = _resolve_ca_bundle()
    ctx = None
    if cafile:
        import ssl

        ctx = ssl.create_default_context(cafile=cafile)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NetworkError(str(exc)) from exc

    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ManifestError("Manifest is not valid JSON.") from exc


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise ManifestError("Manifest must be a JSON object.")

    required_fields = ["runtime_version", "payload_url", "payload_sha256"]
    for field in required_fields:
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"Manifest field '{field}' is missing or invalid.")

    try:
        # Validates dotted numeric format via runtime.parse_version helper.
        is_remote_newer("0.0.0", manifest["runtime_version"])
    except Exception as exc:
        raise ManifestError("Manifest runtime_version is invalid.") from exc

    sha = manifest["payload_sha256"].strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ManifestError("Manifest payload_sha256 must be a lowercase 64-char hex string.")

    if not manifest["payload_url"].startswith("https://"):
        raise ManifestError("Manifest payload_url must be https.")


def download_payload_with_hash(url: str, expected_sha256: str, dest: Path, progress_cb=None) -> None:
    expected = expected_sha256.strip().lower()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    try:
        _download_with_progress(url, dest, progress_cb)
    except Exception as exc:
        raise NetworkError(str(exc)) from exc

    digest = hashlib.sha256()
    with open(dest, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    actual = digest.hexdigest().lower()
    if actual != expected:
        raise IntegrityError(f"Payload hash mismatch. expected={expected} actual={actual}")


def _seed_shared_model_cache() -> None:
    legacy_cache = RUNTIME_DIR / "models" / "huggingface"
    if MODEL_CACHE_DIR.exists() or not legacy_cache.exists():
        return
    MODEL_CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy_cache.rename(MODEL_CACHE_DIR)
        return
    except Exception:
        pass
    shutil.copytree(legacy_cache, MODEL_CACHE_DIR, dirs_exist_ok=True)


def install_runtime_from_payload(payload_path: Path, runtime_version: str) -> None:
    staging_dir = APP_SUPPORT_DIR / f"runtime_staging_{os.getpid()}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    _seed_shared_model_cache()
    _extract_tar(payload_path, staging_dir)
    _clear_quarantine(staging_dir)
    _chmod_runtime_bin(staging_dir)
    _ensure_system_deps()
    _install_runtime(
        runtime_dir=staging_dir,
        runtime_python=staging_dir / "python" / "bin" / "python3",
        runtime_version=runtime_version,
    )
    atomic_swap_runtime(staging_dir, RUNTIME_DIR)


def atomic_swap_runtime(staging_dir: Path, active_dir: Path) -> None:
    backup_dir = active_dir.with_name(active_dir.name + "_prev")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    if active_dir.exists():
        active_dir.rename(backup_dir)

    try:
        staging_dir.rename(active_dir)
    except Exception:
        if backup_dir.exists() and not active_dir.exists():
            backup_dir.rename(active_dir)
        raise

    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def run_startup_update_flow(perform_update: bool = True) -> UpdateDecision:
    messages: list[str] = []
    state: dict = {"checked_at": _now_iso()}
    local_version = _read_local_runtime_version()
    local_compare_version = _normalize_compare_version(local_version)
    state["local_version"] = local_version

    def finalize(action: str, error: str | None = None, manifest: dict | None = None) -> UpdateDecision:
        state["action"] = action
        if error:
            state["error"] = error
        if manifest:
            state["manifest"] = manifest
        _write_startup_update_log(messages)
        _write_update_state(state)
        return UpdateDecision(action=action, messages=messages.copy(), error=error, manifest=manifest)

    if not runtime_installed():
        messages.append("Update Check: no runtime installed, running setup.")
        return finalize("bootstrap_required")

    if local_compare_version != local_version:
        messages.append("Update Check: local runtime version metadata invalid, treating as 0.0.0.")

    messages.append("Update Check: checking manifest...")
    try:
        manifest = fetch_manifest(timeout_s=3)
    except NetworkError as exc:
        msg = f"Update Check: offline, using installed runtime {local_version} ({exc})"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_current")

    try:
        validate_manifest(manifest)
    except ManifestError as exc:
        msg = f"Update Check: manifest invalid, using installed runtime {local_version} ({exc})"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_current")

    remote_version = manifest["runtime_version"].strip()
    state["remote_version"] = remote_version
    payload_url = manifest["payload_url"].strip()
    payload_sha = manifest["payload_sha256"].strip().lower()

    if not is_remote_newer(local_compare_version, remote_version):
        messages.append(f"Update Check: runtime is current ({local_version})")
        return finalize("launch_current")

    messages.append(f"Update Check: update available {local_version} -> {remote_version}")
    if not perform_update:
        return finalize(
            "update_required",
            manifest={
                "runtime_version": remote_version,
                "payload_url": payload_url,
                "payload_sha256": payload_sha,
            },
        )

    messages.append("Update Check: downloading runtime payload...")
    try:
        download_payload_with_hash(payload_url, payload_sha, UPDATE_PAYLOAD_FILE)
    except NetworkError as exc:
        msg = f"Update Check: download unavailable, using installed runtime {local_version} ({exc})"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_current")
    except IntegrityError as exc:
        msg = f"Update Check: blocked (integrity failure): {exc}"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_blocked", error=str(exc))

    messages.append("Update Check: integrity verified")
    try:
        install_runtime_from_payload(UPDATE_PAYLOAD_FILE, remote_version)
    except IntegrityError as exc:
        msg = f"Update Check: blocked (integrity failure): {exc}"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_blocked", error=str(exc))
    except Exception as exc:
        msg = f"Update Check: update failed, using installed runtime {local_version} ({exc})"
        messages.append(msg)
        bootstrap_log(msg)
        return finalize("launch_current")

    messages.append(f"Update Check: update applied ({remote_version})")
    try:
        if UPDATE_PAYLOAD_FILE.exists():
            UPDATE_PAYLOAD_FILE.unlink()
    except Exception:
        pass
    return finalize("updated_and_launch")
