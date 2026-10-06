"""Persist a small incremental-friendly BM25 vocabulary/index artifact."""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from common import DATA_DIR, ensure_data_dirs, record_artifact, write_json


def build() -> dict[str, int]:
    ensure_data_dirs()
    source = DATA_DIR / "chunks/cyber_chunks.jsonl"
    if not source.exists():
        raise RuntimeError("chunks do not exist; run build_chunks.py first")
    chunks = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    document_frequency = Counter()
    inverted: dict[str, list[str]] = {}
    for chunk in chunks:
        terms = set(re.findall(r"[a-z0-9][a-z0-9_.-]+", str(chunk.get("text", "")).lower()))
        for term in terms:
            document_frequency[term] += 1
            inverted.setdefault(term, []).append(chunk["chunk_id"])
    total = max(1, len(chunks))
    index = {"version": "bm25-lite-1", "documents": len(chunks), "average_length": sum(len(str(chunk.get("text", "")).split()) for chunk in chunks) / total, "idf": {term: math.log((total - count + 0.5) / (count + 0.5) + 1) for term, count in document_frequency.items()}, "postings": inverted}
    output = DATA_DIR / "processed/bm25_index.json"
    write_json(output, index)
    record_artifact("bm25_index", output, records=len(chunks), metadata={"terms": len(index["idf"])})
    return {"documents": len(chunks), "terms": len(index["idf"])}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
