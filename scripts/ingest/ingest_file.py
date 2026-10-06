"""Index one local document through the same ingestion path used by the API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import DocumentStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    store = DocumentStore()
    payload = args.path.read_bytes()
    document = store.ingest_bytes(args.path.name, payload, source="local_ingest", source_type="user_document")
    print(json.dumps({"document": document.to_dict(), "chunks": len(store.get_chunks({document.document_id}))}, indent=2))


if __name__ == "__main__":
    main()
