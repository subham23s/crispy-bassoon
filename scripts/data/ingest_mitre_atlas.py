"""Download and normalize MITRE ATLAS data from its official repository."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

from common import DATA_DIR, artifact_path, download_to, ensure_data_dirs, record_artifact, record_error, source_record, upsert_manifest, write_jsonl

URL = "https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/v6/ATLAS-latest.yaml"
LICENSE = "MITRE ATLAS data; review current MITRE terms at https://atlas.mitre.org/resources/terms-of-use/"


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("id") or value.get("external_id"):
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _record(item: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(item.get("type") or item.get("object-type") or item.get("entity_type") or "ATLAS_ENTITY").upper().replace("-", "_")
    if "TACTIC" in raw_type:
        entity_type = "ATLAS_TACTIC"
    elif "MITIGATION" in raw_type or "COURSE" in raw_type:
        entity_type = "ATLAS_MITIGATION"
    elif "RELATION" in raw_type:
        entity_type = "RELATIONSHIP"
    elif "CASE" in raw_type:
        entity_type = "ATLAS_CASE_STUDY"
    else:
        entity_type = "ATLAS_TECHNIQUE"
    return {
        "id": item.get("id") or item.get("external_id", ""),
        "entity_type": entity_type,
        "name": item.get("name", ""),
        "description": item.get("description", "") or item.get("summary", ""),
        "source": "MITRE ATLAS",
        "source_id": item.get("id") or item.get("external_id", ""),
        "version": item.get("version", ""),
        "created_at": item.get("created", ""),
        "updated_at": item.get("modified", ""),
        "references": item.get("references", []) if isinstance(item.get("references", []), list) else [],
        "metadata": item,
        "relationship": {key: item.get(key) for key in ("relationship_type", "source_ref", "target_ref", "source", "target") if key in item},
    }


def ingest(force: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/atlas/ATLAS-latest.yaml"
    normalized = DATA_DIR / "normalized/mitre_atlas.jsonl"
    try:
        download_to(URL, raw, source="MITRE ATLAS", version="v6-latest-pointer", license_name=LICENSE, force=force)
        actual_url = URL
        pointer = raw.read_text(encoding="utf-8").strip()
        if pointer.endswith(".yaml") and "\n" not in pointer:
            actual_url = URL.rsplit("/", 1)[0] + "/" + pointer
            resolved = DATA_DIR / "raw/atlas" / pointer
            download_to(actual_url, resolved, source="MITRE ATLAS", version="v6-latest", license_name=LICENSE, force=force)
            raw = resolved
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to parse official ATLAS YAML; install backend/data dependencies and rerun.") from exc
        parsed = yaml.safe_load(raw.read_text(encoding="utf-8"))
        rows = []
        seen = set()
        for item in _walk(parsed):
            record = _record(item)
            key = (record["id"], record["entity_type"])
            if record["id"] and key not in seen:
                seen.add(key)
                rows.append(record)
        count = write_jsonl(normalized, rows)
        upsert_manifest(source_record(source="MITRE ATLAS", url=actual_url, path=raw, version="v6-latest", records=count, license_name=LICENSE, extra={"entity_types": sorted({row["entity_type"] for row in rows})}))
        record_artifact("normalized_mitre_atlas", normalized, records=count)
        return {"source": "MITRE ATLAS", "records": count, "normalized": artifact_path(normalized), "status": "processed"}
    except Exception as exc:
        record_error("MITRE ATLAS", str(exc), url=URL)
        return {"source": "MITRE ATLAS", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.force), indent=2))


if __name__ == "__main__":
    main()
