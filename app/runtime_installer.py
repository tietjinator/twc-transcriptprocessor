from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


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

    # Create venv
    subprocess.run([py, "-m", "venv", str(venv_dir)], check=True)

    pip = venv_dir / "bin" / "pip"
    subprocess.run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    subprocess.run([str(pip), "install", "-r", str(reqs)], check=True)

    marker.write_text("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
