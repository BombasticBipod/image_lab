"""Project gate: lint, format check, and tests. Exit code 0 means the tree is shippable.

Run with the venv interpreter from the repository root:

    .venv/Scripts/python tools/check.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each step runs through the current interpreter so the venv's tools are used.
STEPS = [
    ("ruff check", [sys.executable, "-m", "ruff", "check", "."]),
    ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
]


def main() -> int:
    for name, cmd in STEPS:
        print(f"== {name}", flush=True)
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            print(f"GATE FAILED at: {name}")
            return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
