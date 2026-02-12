"""
Parakeet model update checks and installs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable


APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Transcript Processor"
STATE_FILE = APP_SUPPORT_DIR / "model_update_state.json"


@dataclass
class ModelUpdateCheckResult:
    status: str
    local_sha: str | None = None
    remote_sha: str | None = None
    should_prompt: bool = False
    message: str = ""
    error: str | None = None


@dataclass
class ModelUpdateApplyResult:
    success: bool
    local_sha: str | None = None
    remote_sha: str | None = None
    message: str = ""
    error: str | None = None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(dt_text: str | None) -> datetime | None:
    if not dt_text:
        return None
    try:
        parsed = datetime.fromisoformat(dt_text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_valid_sha(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[0-9a-f]{40}", value))


def _state_defaults() -> dict[str, Any]:
    return {
        "last_check_at": None,
        "last_remote_sha": None,
        "last_installed_sha": None,
        "deferred_sha": None,
        "last_error": None,
    }


def load_state(state_path: Path = STATE_FILE) -> dict[str, Any]:
    state = _state_defaults()
    try:
        with state_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
            if isinstance(raw, dict):
                state.update(raw)
    except Exception:
        pass
    return state


def save_state(state: dict[str, Any], state_path: Path = STATE_FILE) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _state_defaults()
    payload.update(state)
    fd, temp_path = tempfile.mkstemp(prefix=".model_update_state.", dir=str(state_path.parent))
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
        Path(temp_path).replace(state_path)
    finally:
        leftover = Path(temp_path)
        if leftover.exists():
            leftover.unlink(missing_ok=True)


def should_check_now(state: dict[str, Any], min_interval_hours: int = 24) -> bool:
    last_check = _parse_iso(state.get("last_check_at"))
    if not last_check:
        return True
    return datetime.now(timezone.utc) - last_check >= timedelta(hours=min_interval_hours)


def _repo_cache_dir(cache_dir: Path, repo_id: str) -> Path:
    return cache_dir / f"models--{repo_id.replace('/', '--')}"


def _read_sha_file(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if _is_valid_sha(value):
        return value
    return None


def get_local_model_sha(cache_dir: Path, repo_id: str) -> str | None:
    model_dir = _repo_cache_dir(cache_dir, repo_id)

    # refs/main points to the active default branch commit.
    ref_sha = _read_sha_file(model_dir / "refs" / "main")
    if ref_sha:
        return ref_sha

    snapshots_dir = model_dir / "snapshots"
    if snapshots_dir.exists():
        snapshots = [p for p in snapshots_dir.iterdir() if p.is_dir() and _is_valid_sha(p.name)]
        if snapshots:
            snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return snapshots[0].name

    try:
        from huggingface_hub import snapshot_download

        snapshot_path = Path(
            snapshot_download(
                repo_id=repo_id,
                cache_dir=str(cache_dir),
                local_files_only=True,
            )
        )
    except Exception:
        return None

    if snapshot_path.parent.name == "snapshots" and _is_valid_sha(snapshot_path.name):
        return snapshot_path.name
    return None


def _fetch_remote_model_sha(repo_id: str, timeout_s: float = 3.0) -> tuple[str | None, str | None]:
    result: dict[str, str | None] = {"sha": None, "error": None}

    def _worker() -> None:
        try:
            from huggingface_hub import HfApi

            info = HfApi().model_info(repo_id=repo_id)
            sha = getattr(info, "sha", None)
            result["sha"] = sha if _is_valid_sha(sha) else None
            if not result["sha"]:
                result["error"] = "remote model SHA is missing or invalid"
        except Exception as exc:
            result["error"] = str(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    if thread.is_alive():
        return None, f"timeout after {timeout_s:.0f}s"
    return result["sha"], result["error"]


def get_remote_model_sha(repo_id: str, timeout_s: float = 3.0) -> str | None:
    sha, _ = _fetch_remote_model_sha(repo_id=repo_id, timeout_s=timeout_s)
    return sha


def check_for_update(
    cache_dir: Path,
    repo_id: str,
    *,
    state_path: Path = STATE_FILE,
    min_interval_hours: int = 24,
    timeout_s: float = 3.0,
    force: bool = False,
) -> ModelUpdateCheckResult:
    state = load_state(state_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    local_sha = get_local_model_sha(cache_dir=cache_dir, repo_id=repo_id) or state.get("last_installed_sha")
    if not _is_valid_sha(local_sha):
        local_sha = None

    if not force and not should_check_now(state, min_interval_hours=min_interval_hours):
        known_remote = state.get("last_remote_sha")
        if _is_valid_sha(known_remote) and known_remote != local_sha:
            return ModelUpdateCheckResult(
                status="update_available",
                local_sha=local_sha,
                remote_sha=known_remote,
                should_prompt=False,
                message=f"Model Check: update available ({(local_sha or 'unknown')[:8]} -> {known_remote[:8]})",
            )
        if local_sha:
            return ModelUpdateCheckResult(
                status="up_to_date",
                local_sha=local_sha,
                remote_sha=known_remote if _is_valid_sha(known_remote) else local_sha,
                should_prompt=False,
                message="Model Check: up to date",
            )
        return ModelUpdateCheckResult(
            status="skipped",
            should_prompt=False,
            message="Model Check: recent check found no update",
        )

    remote_sha, fetch_error = _fetch_remote_model_sha(repo_id=repo_id, timeout_s=timeout_s)
    state["last_check_at"] = _iso_now()

    if not remote_sha:
        state["last_error"] = fetch_error or "could not fetch remote model metadata"
        save_state(state, state_path=state_path)
        if local_sha:
            return ModelUpdateCheckResult(
                status="offline",
                local_sha=local_sha,
                should_prompt=False,
                message="Model Check: offline, using installed model",
                error=state["last_error"],
            )
        return ModelUpdateCheckResult(
            status="error",
            local_sha=None,
            should_prompt=False,
            message=f"Model Check: could not verify updates ({state['last_error']})",
            error=state["last_error"],
        )

    state["last_remote_sha"] = remote_sha
    state["last_error"] = None

    if local_sha == remote_sha:
        state["last_installed_sha"] = local_sha
        if state.get("deferred_sha") == remote_sha:
            state["deferred_sha"] = None
        save_state(state, state_path=state_path)
        return ModelUpdateCheckResult(
            status="up_to_date",
            local_sha=local_sha,
            remote_sha=remote_sha,
            should_prompt=False,
            message="Model Check: up to date",
        )

    save_state(state, state_path=state_path)
    return ModelUpdateCheckResult(
        status="update_available",
        local_sha=local_sha,
        remote_sha=remote_sha,
        should_prompt=True,
        message=f"Model Check: update available ({(local_sha or 'unknown')[:8]} -> {remote_sha[:8]})",
    )


def mark_deferred(remote_sha: str, state_path: Path = STATE_FILE) -> None:
    state = load_state(state_path)
    state["deferred_sha"] = remote_sha if _is_valid_sha(remote_sha) else None
    state["last_check_at"] = _iso_now()
    save_state(state, state_path=state_path)


def apply_update(
    cache_dir: Path,
    repo_id: str,
    *,
    remote_sha: str | None = None,
    state_path: Path = STATE_FILE,
    timeout_s: float = 3.0,
    progress_callback: Callable[[str], None] | None = None,
) -> ModelUpdateApplyResult:
    state = load_state(state_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not remote_sha:
        remote_sha, fetch_error = _fetch_remote_model_sha(repo_id=repo_id, timeout_s=timeout_s)
        if not remote_sha:
            state["last_error"] = fetch_error or "could not fetch remote model metadata"
            save_state(state, state_path=state_path)
            return ModelUpdateApplyResult(
                success=False,
                message=f"Model Check: update failed ({state['last_error']})",
                error=state["last_error"],
            )

    try:
        if progress_callback:
            progress_callback("Model Check: update started")
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=repo_id,
            revision=remote_sha,
            cache_dir=str(cache_dir),
            resume_download=True,
        )
        # Write refs/main to match the newly installed revision for quick local detection.
        refs_main = _repo_cache_dir(cache_dir, repo_id) / "refs" / "main"
        refs_main.parent.mkdir(parents=True, exist_ok=True)
        refs_main.write_text(f"{remote_sha}\n", encoding="utf-8")
    except Exception as exc:
        state["last_error"] = str(exc)
        save_state(state, state_path=state_path)
        return ModelUpdateApplyResult(
            success=False,
            remote_sha=remote_sha,
            message=f"Model Check: update failed ({exc})",
            error=str(exc),
        )

    state["last_check_at"] = _iso_now()
    state["last_remote_sha"] = remote_sha
    state["last_installed_sha"] = remote_sha
    state["deferred_sha"] = None
    state["last_error"] = None
    save_state(state, state_path=state_path)
    if progress_callback:
        progress_callback("Model Check: update complete")
    return ModelUpdateApplyResult(
        success=True,
        local_sha=remote_sha,
        remote_sha=remote_sha,
        message="Model Check: update complete",
    )
