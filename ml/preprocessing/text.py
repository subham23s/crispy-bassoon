"""Dependency-light dataset readers used by model training scripts."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def read_json_splits(path: str | Path, label_key: str = "intent") -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    output: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "validation", "test"):
        rows = payload.get(split, [])
        output[split] = [{"text": str(row.get("text", "")), "label": str(row.get(label_key, row.get("label", ""))), **row} for row in rows if str(row.get("text", "")).strip()]
    return output


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_pair_dataset(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                rows.append({"text": str(row.get("query", "")), "text_pair": str(row.get("document", row.get("evidence", ""))), "label": int(row.get("relevance", row.get("label", 0))), **row})
    return rows
