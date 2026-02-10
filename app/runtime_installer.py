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
    venv_python = venv_dir / "bin" / "python"
    subprocess.run(
        [
            str(venv_python),
            "-c",
            "from parakeet_mlx import from_pretrained; from_pretrained('mlx-community/parakeet-tdt-0.6b-v3')",
        ],
        check=True,
        env=env,
    )

    marker.write_text("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
