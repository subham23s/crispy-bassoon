"""Aggregate source-specific records into deduplicated entities and edges."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, artifact_path, ensure_data_dirs, read_jsonl, record_artifact, write_jsonl


def normalize() -> dict[str, int]:
    ensure_data_dirs()
    source_files = [path for path in sorted((DATA_DIR / "normalized").glob("*.jsonl")) if path.name not in {"cyber_entities.jsonl", "cyber_relationships.jsonl"}]
    entities: dict[tuple[str, str, str], dict[str, Any]] = {}
    pending_relationships: list[tuple[str, dict[str, Any]]] = []
    for path in source_files:
        for row in read_jsonl(path):
            entity_type = str(row.get("entity_type", "UNKNOWN"))
            source = str(row.get("source", path.stem))
            source_id = str(row.get("source_id") or row.get("id") or "")
            if not source_id:
                continue
            if entity_type == "RELATIONSHIP" and isinstance(row.get("relationship"), dict):
                pending_relationships.append((source, {**row, "source_record_id": source_id}))
                continue
            entity_id = f"{source.lower().replace(' ', '_')}:{source_id}"
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
            entity = {
                "id": entity_id,
                "entity_type": entity_type,
                "name": str(row.get("name", "")),
                "description": row.get("description", "") if isinstance(row.get("description", ""), str) else json.dumps(row.get("description", {}), ensure_ascii=False),
                "source": source,
                "source_id": source_id,
                "version": row.get("version", ""),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
                "references": row.get("references", []),
                "metadata": metadata,
                "source_file": artifact_path(path),
            }
            # Preserve aliases used by official relationship formats (STIX IDs,
            # external IDs, and source-specific identifiers).
            aliases = {source_id, str(row.get("id", ""))}
            for key in ("stix_id", "id", "external_id", "source_id"):
                if metadata.get(key):
                    aliases.add(str(metadata[key]))
            entity["aliases"] = sorted(alias for alias in aliases if alias)
            entities[(source, source_id, entity_type)] = entity

    alias_map: dict[str, str] = {}
    for entity in entities.values():
        for alias in entity.get("aliases", []):
            alias_map.setdefault(str(alias), entity["id"])
        alias_map.setdefault(entity["id"], entity["id"])
    relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
    entity_ids = {item["id"] for item in entities.values()}
    for source, row in pending_relationships:
        relationship = row.get("relationship", {})
        source_ref = relationship.get("source_ref") or relationship.get("source") or relationship.get("source_entity_id")
        target_ref = relationship.get("target_ref") or relationship.get("target") or relationship.get("target_entity_id")
        relation_type = relationship.get("relationship_type") or relationship.get("type") or "related_to"
        source_id = alias_map.get(str(source_ref), str(source_ref or ""))
        target_id = alias_map.get(str(target_ref), str(target_ref or ""))
        if not source_id or not target_id:
            continue
        key = (source_id, str(relation_type), target_id)
        relationships[key] = {
            "id": f"relationship:{source_id}:{relation_type}:{target_id}",
            "source_entity_id": source_id,
            "relationship_type": str(relation_type),
            "target_entity_id": target_id,
            "source": source,
            "source_record_id": str(row.get("source_record_id", "")),
            "evidence": row.get("references", []),
            "resolved": source_id in entity_ids and target_id in entity_ids,
        }
    entity_path = DATA_DIR / "normalized/cyber_entities.jsonl"
    relationship_path = DATA_DIR / "normalized/cyber_relationships.jsonl"
    entity_count = write_jsonl(entity_path, sorted(entities.values(), key=lambda row: row["id"]))
    relationship_count = write_jsonl(relationship_path, sorted(relationships.values(), key=lambda row: row["id"]))
    record_artifact("cyber_entities", entity_path, records=entity_count)
    record_artifact("cyber_relationships", relationship_path, records=relationship_count)
    return {"source_files": len(source_files), "entities": entity_count, "relationships": relationship_count, "resolved_relationships": sum(bool(row.get("resolved")) for row in relationships.values())}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(normalize(), indent=2))


if __name__ == "__main__":
    main()
