"""Build deterministic local embeddings after normalized chunks exist.

The default `tfidf-lite`/feature-hash representation is a reproducible CPU
baseline, not a transformer model. Transformer downloads are explicit and not
performed automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from common import DATA_DIR, ensure_data_dirs, read_jsonl, record_artifact, utc_now, write_jsonl


def _tokens(text: str) -> list[str]:
    import re
    return [item for item in re.findall(r"[a-z0-9][a-z0-9_.-]+", text.lower()) if len(item) > 2]


def _vector(text: str, dimension: int) -> list[float]:
    values = [0.0] * dimension
    counts = Counter(_tokens(text))
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 else -1.0
        values[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in values))
    return [round(value / norm, 8) if norm else 0.0 for value in values]


def build(model: str = "tfidf-lite", dimension: int = 256) -> dict[str, object]:
    ensure_data_dirs()
    chunks_path = DATA_DIR / "chunks/cyber_chunks.jsonl"
    if not chunks_path.exists():
        raise RuntimeError("normalized chunks do not exist; run normalize_data.py and build_chunks.py first")
    if model != "tfidf-lite":
        raise RuntimeError("Only the explicit local tfidf-lite baseline is available; configure a transformer separately rather than silently downloading one.")
    output = DATA_DIR / "embeddings/tfidf-lite.jsonl"
    old = {row.get("chunk_id"): row for row in read_jsonl(output)}
    rows = []
    for chunk in read_jsonl(chunks_path):
        checksum = hashlib.sha256(str(chunk.get("text", "")).encode()).hexdigest()
        previous = old.get(chunk.get("chunk_id"))
        if previous and previous.get("text_checksum") == checksum and previous.get("embedding_model") == model and previous.get("dimension") == dimension:
            rows.append(previous)
            continue
        rows.append({"chunk_id": chunk["chunk_id"], "document_id": chunk["document_id"], "embedding_model": model, "dimension": dimension, "vector": _vector(str(chunk.get("text", "")), dimension), "text_checksum": checksum, "created_at": utc_now()})
    count = write_jsonl(output, rows)
    record_artifact("tfidf_lite_embeddings", output, records=count, metadata={"embedding_model": model, "dimension": dimension})
    return {"embedding_model": model, "dimension": dimension, "records": count, "status": "processed"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="tfidf-lite")
    parser.add_argument("--dimension", type=int, default=256)
    args = parser.parse_args()
    print(json.dumps(build(args.model, args.dimension), indent=2))


if __name__ == "__main__":
    main()
