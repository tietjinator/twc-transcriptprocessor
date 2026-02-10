from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _emit_step(step: int, total: int, message: str) -> None:
    print(f"TPP_STEP:{step}/{total}:{message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--requirements", required=True)
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    reqs = Path(args.requirements)
    venv_dir = runtime_dir / "venv"
    marker = runtime_dir / ".installed"

    py = sys.executable

    # Ensure the portable Python is executable (quarantine/permissions)
    try:
        os.chmod(py, 0o755)
    except Exception:
        pass

    total_steps = 4

    _emit_step(1, total_steps, "Creating virtual environment")
    subprocess.run([py, "-m", "venv", str(venv_dir)], check=True)

    _emit_step(2, total_steps, "Upgrading pip tooling")
    pip = venv_dir / "bin" / "pip"
    subprocess.run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)

    _emit_step(3, total_steps, "Installing Python dependencies")
    subprocess.run([str(pip), "install", "-r", str(reqs)], check=True)

    _emit_step(4, total_steps, "Downloading Parakeet model (first run)")
    model_cache = runtime_dir / "models" / "huggingface"
    model_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HUGGINGFACE_HUB_CACHE"] = str(model_cache)
    env["HF_HOME"] = str(model_cache)
    # Force standard HTTP downloads so tqdm emits incremental byte progress.
    env["HF_HUB_DISABLE_XET"] = "1"
    venv_python = venv_dir / "bin" / "python"
    subprocess.run(
        [
            str(venv_python),
            "-c",
            """
import json
import threading
import time
from huggingface_hub import HfApi, hf_hub_download
import os
from pathlib import Path

repo_id = "mlx-community/parakeet-tdt-0.6b-v3"
cache_dir = os.environ.get("HUGGINGFACE_HUB_CACHE") or os.environ.get("HF_HOME")

api = HfApi()
info = api.model_info(repo_id)
siblings = [s for s in info.siblings if s.rfilename and not s.rfilename.endswith(".gitattributes")]
siblings = sorted(siblings, key=lambda s: s.rfilename)

size_map = {}
for item in api.list_repo_tree(repo_id, recursive=False, expand=True):
    if getattr(item, "path", None):
        size_map[item.path] = int(getattr(item, "size", 0) or 0)

blob_dir = Path(cache_dir) / ("models--" + repo_id.replace("/", "--")) / "blobs"

def current_partial_bytes() -> int:
    if not blob_dir.exists():
        return 0
    sizes = []
    for p in blob_dir.glob("*.incomplete"):
        try:
            sizes.append(p.stat().st_size)
        except OSError:
            pass
    return max(sizes) if sizes else 0

total_size = sum((s.size or 0) for s in siblings)
total_units = total_size if total_size > 0 else len(siblings)
downloaded = 0

for idx, s in enumerate(siblings, 1):
    file_size = int(size_map.get(s.rfilename, s.size or 0))
    print("TPP_FILE_START:" + json.dumps({
        "index": idx,
        "total_files": len(siblings),
        "file": s.rfilename,
        "size": file_size
    }), flush=True)

    stop_hb = threading.Event()
    started_at = time.time()
    emitted_done = {"value": -1}

    def heartbeat():
        while not stop_hb.wait(1.0):
            done = current_partial_bytes()
            total = file_size
            pct = int((done / total) * 100) if total > 0 else 0
            if done != emitted_done["value"]:
                emitted_done["value"] = done
                print("TPP_FILE_PROGRESS:" + json.dumps({
                    "index": idx,
                    "total_files": len(siblings),
                    "file": s.rfilename,
                    "done": done,
                    "total": total,
                    "pct": pct
                }), flush=True)
            print("TPP_FILE_HEARTBEAT:" + json.dumps({
                "index": idx,
                "total_files": len(siblings),
                "file": s.rfilename,
                "elapsed": int(time.time() - started_at),
                "size": file_size,
                "done": done,
                "total": total
            }), flush=True)

    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()
    try:
        hf_hub_download(
            repo_id=repo_id,
            filename=s.rfilename,
            cache_dir=cache_dir,
        )
    finally:
        stop_hb.set()
        hb.join(timeout=0.2)

    print("TPP_FILE_PROGRESS:" + json.dumps({
        "index": idx,
        "total_files": len(siblings),
        "file": s.rfilename,
        "done": file_size or emitted_done["value"],
        "total": file_size or emitted_done["value"],
        "pct": 100
    }), flush=True)

    if total_size > 0:
        downloaded += file_size or emitted_done["value"]
        units_done = downloaded
    else:
        units_done = idx
    pct = int((units_done / total_units) * 100) if total_units else 0
    print(f"TPP_DOWNLOAD:{units_done}/{total_units}:{pct}", flush=True)
""",
        ],
        check=True,
        env=env,
    )

    marker.write_text("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
