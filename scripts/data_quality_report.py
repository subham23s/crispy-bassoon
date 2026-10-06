"""Print counts, missing metadata, duplicates, errors, and update timestamps."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.data.common import ROOT, read_jsonl, read_manifest  # noqa: E402


def report() -> dict[str, object]:
    manifest = read_manifest()
    counts: dict[str, int] = {}
    for path in (ROOT / "data/normalized").glob("*.jsonl"):
        rows = list(read_jsonl(path))
        counts[path.name] = len(rows)
    entities = list(read_jsonl(ROOT / "data/normalized/cyber_entities.jsonl"))
    missing_metadata = sum(not row.get("source") or not row.get("source_id") for row in entities)
    duplicates = len(entities) - len({row.get("id") for row in entities})
    intent_rows = []
    intent_path = ROOT / "data/ml/intent/intent_dataset.csv"
    if intent_path.exists():
        with intent_path.open(encoding="utf-8", newline="") as handle:
            intent_rows = list(csv.DictReader(handle))
    result = {"documents_by_artifact": counts, "entities": len(entities), "relationships": len(list(read_jsonl(ROOT / "data/normalized/cyber_relationships.jsonl"))), "entity_types": dict(Counter(row.get("entity_type", "UNKNOWN") for row in entities)), "missing_provenance": missing_metadata, "duplicate_entity_ids": duplicates, "manifest_errors": len(manifest.get("errors", [])), "last_manifest_update": manifest.get("updated_at"), "sources": manifest.get("sources", []), "intent_examples": len(intent_rows), "intent_class_distribution": dict(Counter(row.get("intent", "") for row in intent_rows)), "intent_duplicate_rate": (len(intent_rows) - len({row.get("text", "") for row in intent_rows})) / max(1, len(intent_rows)), "status": "warning" if missing_metadata or duplicates or manifest.get("errors") else "ok"}
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    argparse.ArgumentParser().parse_args()
    report()


if __name__ == "__main__":
    main()
