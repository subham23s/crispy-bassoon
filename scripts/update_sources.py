"""Refresh configured authoritative sources with bounded retry/backoff."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.source_refresh import SOURCES, run_refresh  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES), default=None)
    parser.add_argument("--no-nvd-update", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = run_refresh(args.sources, update_nvd=not args.no_nvd_update, force=args.force)
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report["failures"] else 0)


if __name__ == "__main__":
    main()
