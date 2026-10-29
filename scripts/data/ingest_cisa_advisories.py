"""Acquire the explicitly configured CISA advisory PDFs and extract full text."""
from __future__ import annotations

import json

from ingest_reference_pages import ingest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest("cisa_advisories", "CISA", "cisa_advisories", args.force), indent=2))
