"""Run the API from the repository root without installing the package."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.main import run  # noqa: E402


if __name__ == "__main__":
    run()
