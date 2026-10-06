"""Build a persistent local vector index from the reproducible embeddings.

The local index is deliberately dependency-light: SQLite stores normalized
vectors and metadata, with a document index for filtering. It is a real,
persistent vector store and can be migrated to pgvector without changing the
embedding artifact format.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from common import ROOT, DATA_DIR, artifact_path, ensure_data_dirs, read_jsonl, record_artifact, utc_now


def build(*, embedding_path: str = "data/embeddings/tfidf-lite.jsonl") -> dict[str, Any]:
    ensure_data_dirs()
    embeddings = DATA_DIR / "embeddings/tfidf-lite.jsonl" if embedding_path == "data/embeddings/tfidf-lite.jsonl" else ROOT / embedding_path
    if not embeddings.exists():
        raise RuntimeError(f"embedding artifact is missing: {embeddings}; run build_embeddings.py first")
    output = DATA_DIR / "processed/vector_index.sqlite"
    temporary = output.with_suffix(".sqlite.part")
    if temporary.exists():
        temporary.unlink()
    rows = list(read_jsonl(embeddings))
    if not rows:
        raise RuntimeError("embedding artifact contains no vectors; refusing to create an empty index")
    dimension = int(rows[0].get("dimension", 0))
    if dimension <= 0:
        raise RuntimeError("embedding dimension must be positive")
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE vector_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE vectors (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                text_checksum TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_vectors_document ON vectors(document_id);
            CREATE INDEX idx_vectors_model_dimension ON vectors(model_name, dimension);
            """
        )
        connection.executemany(
            "INSERT INTO vectors(chunk_id, document_id, model_name, dimension, vector_json, text_checksum, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    str(row["chunk_id"]),
                    str(row["document_id"]),
                    str(row.get("embedding_model", "unknown")),
                    int(row.get("dimension", dimension)),
                    json.dumps(row.get("vector", []), separators=(",", ":")),
                    str(row.get("text_checksum", "")),
                    str(row.get("created_at", utc_now())),
                )
                for row in rows
            ],
        )
        metadata = {
            "schema_version": "1",
            "model_name": str(rows[0].get("embedding_model", "unknown")),
            "dimension": str(dimension),
            "vectors": str(len(rows)),
            "generated_at": utc_now(),
        }
        connection.executemany("INSERT INTO vector_metadata(key, value) VALUES (?, ?)", metadata.items())
        connection.commit()
    finally:
        connection.close()
    temporary.replace(output)
    record_artifact("vector_index", output, records=len(rows), metadata={"model_name": rows[0].get("embedding_model"), "dimension": dimension, "index_type": "sqlite-persistent-vector-store"})
    return {"status": "processed", "vectors": len(rows), "dimension": dimension, "model_name": rows[0].get("embedding_model"), "path": artifact_path(output)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding-path", default="data/embeddings/tfidf-lite.jsonl")
    args = parser.parse_args()
    print(json.dumps(build(embedding_path=args.embedding_path), indent=2))


if __name__ == "__main__":
    main()
