"""Download and normalize the official MITRE ATT&CK STIX bundle.

The script is repeatable: unchanged raw files are reused and normalized output
is replaced atomically. It never fabricates ATT&CK entities or relationships.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, artifact_path, download_to, ensure_data_dirs, load_json, record_artifact, record_error, source_record, upsert_manifest, write_jsonl

URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"
LICENSE = "MITRE ATT&CK data; review current MITRE terms at https://attack.mitre.org/resources/terms-of-use/"


def _entity_type(obj: dict[str, Any]) -> str:
    mapping = {
        "attack-pattern": "ATTACK_TECHNIQUE",
        "x-mitre-tactic": "ATTACK_TACTIC",
        "intrusion-set": "THREAT_ACTOR",
        "malware": "MALWARE",
        "tool": "SOFTWARE",
        "campaign": "CAMPAIGN",
        "course-of-action": "MITIGATION",
        "relationship": "RELATIONSHIP",
        "x-mitre-data-source": "DATA_SOURCE",
        "x-mitre-data-component": "DATA_COMPONENT",
    }
    return mapping.get(str(obj.get("type")), str(obj.get("type", "UNKNOWN")).upper())


def _record(obj: dict[str, Any]) -> dict[str, Any]:
    refs = []
    for ref in obj.get("external_references", []) or []:
        if isinstance(ref, dict):
            refs.append({"source_name": ref.get("source_name", ""), "external_id": ref.get("external_id", ""), "url": ref.get("url", "")})
    entity_type = _entity_type(obj)
    return {
        "id": obj.get("id", ""),
        "entity_type": entity_type,
        "name": obj.get("name", ""),
        "description": obj.get("description", ""),
        "source": "MITRE ATT&CK",
        "source_id": next((ref.get("external_id") for ref in refs if str(ref.get("external_id", "")).startswith(("T", "G", "S", "C", "M"))), obj.get("id", "")),
        "version": obj.get("x_mitre_version", ""),
        "created_at": obj.get("created", ""),
        "updated_at": obj.get("modified", ""),
        "references": refs,
        "metadata": {key: value for key, value in obj.items() if key.startswith("x_mitre_") and key not in {"x_mitre_version"}},
        "source_object": obj.get("type", ""),
        "relationship": {key: obj.get(key) for key in ("relationship_type", "source_ref", "target_ref") if key in obj} if entity_type == "RELATIONSHIP" else None,
    }


def ingest(force: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/mitre/enterprise-attack.json"
    normalized = DATA_DIR / "normalized/mitre_attack.jsonl"
    try:
        download_to(URL, raw, source="MITRE ATT&CK", version="repository-master", license_name=LICENSE, force=force)
        bundle = load_json(raw)
        objects = [obj for obj in bundle.get("objects", []) if isinstance(obj, dict) and not obj.get("revoked") and not obj.get("x_mitre_deprecated")]
        rows = [_record(obj) for obj in objects]
        count = write_jsonl(normalized, rows)
        version = str(bundle.get("id", "repository-master"))
        upsert_manifest(source_record(source="MITRE ATT&CK", url=URL, path=raw, version=version, records=count, license_name=LICENSE, extra={"object_types": sorted({row["entity_type"] for row in rows})}))
        record_artifact("normalized_mitre_attack", normalized, records=count)
        return {"source": "MITRE ATT&CK", "records": count, "raw": artifact_path(raw), "normalized": artifact_path(normalized), "status": "processed"}
    except Exception as exc:
        record_error("MITRE ATT&CK", str(exc), url=URL)
        return {"source": "MITRE ATT&CK", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.force), indent=2))


if __name__ == "__main__":
    main()
