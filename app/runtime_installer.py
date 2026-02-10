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
from huggingface_hub import HfApi, hf_hub_download
from tqdm.auto import tqdm
import os

repo_id = "mlx-community/parakeet-tdt-0.6b-v3"
cache_dir = os.environ.get("HUGGINGFACE_HUB_CACHE") or os.environ.get("HF_HOME")

api = HfApi()
info = api.model_info(repo_id)
siblings = [s for s in info.siblings if s.rfilename and not s.rfilename.endswith(".gitattributes")]
siblings = sorted(siblings, key=lambda s: s.rfilename)

class EmitTqdm(tqdm):
    current_file = ""
    current_index = 0
    total_files = 0
    file_size = 0

    def __init__(self, *args, **kwargs):
        kwargs["disable"] = True
        super().__init__(*args, **kwargs)
        self.last_pct = -1

    def update(self, n=1):
        out = super().update(n)
        total = int(self.total or self.file_size or 0)
        done = int(self.n)
        pct = int((done / total) * 100) if total > 0 else 0
        if pct != self.last_pct:
            print("TPP_FILE_PROGRESS:" + json.dumps({
                "index": self.current_index,
                "total_files": self.total_files,
                "file": self.current_file,
                "done": done,
                "total": total,
                "pct": pct
            }), flush=True)
            self.last_pct = pct
        return out

total_size = sum((s.size or 0) for s in siblings)
total_units = total_size if total_size > 0 else len(siblings)
downloaded = 0

for idx, s in enumerate(siblings, 1):
    file_size = int(s.size or 0)
    print("TPP_FILE_START:" + json.dumps({
        "index": idx,
        "total_files": len(siblings),
        "file": s.rfilename,
        "size": file_size
    }), flush=True)

    EmitTqdm.current_file = s.rfilename
    EmitTqdm.current_index = idx
    EmitTqdm.total_files = len(siblings)
    EmitTqdm.file_size = file_size

    hf_hub_download(
        repo_id=repo_id,
        filename=s.rfilename,
        cache_dir=cache_dir,
        resume_download=True,
        tqdm_class=EmitTqdm,
    )

    print("TPP_FILE_PROGRESS:" + json.dumps({
        "index": idx,
        "total_files": len(siblings),
        "file": s.rfilename,
        "done": file_size,
        "total": file_size,
        "pct": 100
    }), flush=True)

    if total_size > 0:
        downloaded += file_size
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
