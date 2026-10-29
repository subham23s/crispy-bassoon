"""Ingest curated official cybersecurity tool documentation."""
from __future__ import annotations

import argparse
import json

from ingest_reference_pages import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-download configured tool documentation")
    args = parser.parse_args()
    print(json.dumps(ingest("tools", "Security Tools", "tools", args.force), indent=2))


if __name__ == "__main__":
    main()
