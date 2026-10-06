"""Build section/sentence-aware chunks from normalized entities."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import DATA_DIR, ensure_data_dirs, read_jsonl, record_artifact, write_jsonl


def _sentence_chunks(text: str, max_chars: int) -> list[tuple[str, int, int]]:
    pieces = [match for match in re.finditer(r"[^.!?\n]+[.!?]?", text) if match.group(0).strip()]
    chunks: list[tuple[str, int, int]] = []
    buffer: list[str] = []
    start = pieces[0].start() if pieces else 0
    end = start
    for piece in pieces:
        value = " ".join(piece.group(0).split())
        if not value:
            continue
        if buffer and len(" ".join(buffer)) + len(value) + 1 > max_chars:
            chunk = " ".join(buffer).strip()
            chunks.append((chunk, start, end))
            buffer = []
            start = piece.start()
        buffer.append(value)
        end = piece.end()
    if buffer:
        chunks.append((" ".join(buffer).strip(), start, end))
    return chunks or [(text.strip(), 0, len(text))]


def build(max_chars: int = 1200) -> dict[str, int]:
    ensure_data_dirs()
    source = DATA_DIR / "normalized/cyber_entities.jsonl"
    output = DATA_DIR / "chunks/cyber_chunks.jsonl"
    rows = []
    for entity in read_jsonl(source):
        description = entity.get("description", "")
        if not isinstance(description, str):
            description = json.dumps(description, ensure_ascii=False)
        text = f"{entity.get('name', '')}\n{description}".strip()
        for ordinal, (chunk_text, start, end) in enumerate(_sentence_chunks(text, max_chars)):
            if not chunk_text:
                continue
            rows.append({
                "chunk_id": f"{entity['id']}:chunk:{ordinal}",
                "document_id": entity["id"],
                "text": chunk_text,
                "page": None,
                "section": entity.get("entity_type", ""),
                "start_char": start,
                "end_char": end,
                "metadata": {
                    "source": entity.get("source", ""),
                    "source_id": entity.get("source_id", ""),
                    "source_file": entity.get("source_file", ""),
                    "version": entity.get("version", ""),
                    "references": entity.get("references", []),
                },
            })
    count = write_jsonl(output, rows)
    record_artifact("cyber_chunks", output, records=count, metadata={"chunk_strategy": "sentence-aware", "max_chars": max_chars})
    print(json.dumps({"chunks": count, "source_entities": len(list(read_jsonl(source))), "strategy": "sentence-aware", "max_chars": max_chars}, indent=2))
    return {"chunks": count}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()
    build(args.max_chars)


if __name__ == "__main__":
    main()
