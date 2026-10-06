"""Download CISA's official Known Exploited Vulnerabilities JSON catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, artifact_path, download_to, ensure_data_dirs, load_json, record_artifact, record_error, source_record, upsert_manifest, write_jsonl

URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
LICENSE = "CISA public catalog; follow CISA terms and attribution requirements."


def _record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("cveID", ""),
        "entity_type": "CVE",
        "name": item.get("vulnerabilityName", ""),
        "description": item.get("shortDescription", ""),
        "source": "CISA KEV",
        "source_id": item.get("cveID", ""),
        "version": "catalog",
        "created_at": item.get("dateAdded", ""),
        "updated_at": item.get("dueDate", ""),
        "references": [],
        "metadata": {
            "vendorProject": item.get("vendorProject", ""),
            "product": item.get("product", ""),
            "dateAdded": item.get("dateAdded", ""),
            "dueDate": item.get("dueDate", ""),
            "knownRansomwareCampaignUse": item.get("knownRansomwareCampaignUse", ""),
            "notes": item.get("notes", ""),
            "requiredAction": item.get("requiredAction", ""),
        },
    }


def ingest(force: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/cisa/known_exploited_vulnerabilities.json"
    normalized = DATA_DIR / "normalized/cisa_kev.jsonl"
    try:
        download_to(URL, raw, source="CISA KEV", version="current-feed", license_name=LICENSE, force=force)
        data = load_json(raw)
        rows = [_record(item) for item in data.get("vulnerabilities", []) if isinstance(item, dict) and item.get("cveID")]
        count = write_jsonl(normalized, rows)
        version = str(data.get("catalogVersion", "current-feed"))
        upsert_manifest(source_record(source="CISA KEV", url=URL, path=raw, version=version, records=count, license_name=LICENSE))
        record_artifact("normalized_cisa_kev", normalized, records=count)
        return {"source": "CISA KEV", "records": count, "catalog_version": version, "normalized": artifact_path(normalized), "status": "processed"}
    except Exception as exc:
        record_error("CISA KEV", str(exc), url=URL)
        return {"source": "CISA KEV", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.force), indent=2))


if __name__ == "__main__":
    main()
