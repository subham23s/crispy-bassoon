"""Validate source and derived data artifacts without inventing missing records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, artifact_path, ensure_data_dirs, read_jsonl, record_artifact, utc_now, write_json


def _validate_jsonl(path: Path, required: tuple[str, ...]) -> dict[str, Any]:
    errors: list[str] = []
    rows = 0
    identifiers: set[str] = set()
    if not path.exists():
        return {"path": artifact_path(path), "status": "missing", "records": 0, "errors": ["artifact is missing"]}
    try:
        for number, row in enumerate(read_jsonl(path), start=1):
            rows += 1
            missing = [field for field in required if not str(row.get(field, "")).strip()]
            if missing:
                errors.append(f"line {number}: missing required fields {missing}")
            identifier = str(row.get("id") or row.get("source_id") or row.get("chunk_id") or "")
            if identifier in identifiers:
                errors.append(f"line {number}: duplicate identifier {identifier}")
            if identifier:
                identifiers.add(identifier)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"parse error: {exc}")
    return {"path": artifact_path(path), "status": "valid" if not errors else "invalid", "records": rows, "errors": errors[:50]}


def validate() -> dict[str, Any]:
    ensure_data_dirs()
    checks = []
    normalized_dir = DATA_DIR / "normalized"
    for path in sorted(normalized_dir.glob("*.jsonl")):
        if path.name == "cyber_entities.jsonl":
            checks.append(_validate_jsonl(path, ("id", "entity_type", "source")))
        elif path.name == "cyber_relationships.jsonl":
            checks.append(_validate_jsonl(path, ("id", "relationship_type")))
        else:
            checks.append(_validate_jsonl(path, ("id", "source", "entity_type")))
    chunks = DATA_DIR / "chunks/cyber_chunks.jsonl"
    if chunks.exists():
        checks.append(_validate_jsonl(chunks, ("chunk_id", "document_id", "text")))
    embeddings = DATA_DIR / "embeddings/tfidf-lite.jsonl"
    if embeddings.exists():
        checks.append(_validate_jsonl(embeddings, ("chunk_id", "document_id", "embedding_model", "vector")))
    errors = [error for check in checks for error in check.get("errors", [])]
    result = {
        "status": "valid" if not errors else "invalid",
        "generated_at": utc_now(),
        "checks": checks,
        "totals": {
            "normalized_records": sum(check.get("records", 0) for check in checks if "normalized/" in check.get("path", "")),
            "chunks": sum(check.get("records", 0) for check in checks if "chunks/" in check.get("path", "")),
            "embeddings": sum(check.get("records", 0) for check in checks if "embeddings/" in check.get("path", "")),
        },
        "errors": errors[:100],
        "note": "Missing source artifacts are reported as missing; no records are generated to satisfy validation.",
    }
    output = DATA_DIR / "processed/data_validation.json"
    write_json(output, result)
    record_artifact("data_validation", output, records=len(checks))
    return result


def main() -> None:
    result = validate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "valid" else 2)


if __name__ == "__main__":
    main()
