"""Public entry point for the reproducible CyberSecRA-X data bootstrap."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "data"))
from bootstrap_data import main  # noqa: E402


if __name__ == "__main__":
    main()
