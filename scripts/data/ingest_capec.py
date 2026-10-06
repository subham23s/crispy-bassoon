"""Download and normalize the latest official CAPEC XML archive."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from common import DATA_DIR, artifact_path, download_to, ensure_data_dirs, record_artifact, record_error, source_record, upsert_manifest, write_jsonl

URL = "https://capec.mitre.org/data/archive/capec_latest.zip"
LICENSE = "CAPEC data; subject to MITRE CAPEC terms of use."


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def ingest(force: bool = False) -> dict[str, object]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/capec/capec_latest.zip"
    normalized = DATA_DIR / "normalized/capec.jsonl"
    try:
        download_to(URL, raw, source="CAPEC", version="latest", license_name=LICENSE, force=force)
        with zipfile.ZipFile(raw) as archive:
            xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
            if not xml_name:
                raise RuntimeError("CAPEC archive did not contain XML")
            root = ET.fromstring(archive.read(xml_name))
        rows = []
        for element in root.iter():
            if _local(element.tag) not in {"Attack_Pattern", "Category", "View"}:
                continue
            identifier = element.attrib.get("ID", "")
            if not identifier:
                continue
            refs = []
            for ref in element.iter():
                if _local(ref.tag) in {"Reference", "External_Reference"}:
                    refs.append({"id": ref.attrib.get("Reference_ID", ""), "url": ref.attrib.get("URL", "")})
            rows.append({
                "id": f"CAPEC-{identifier}" if not identifier.startswith("CAPEC-") else identifier,
                "entity_type": "CAPEC_CATEGORY" if _local(element.tag) == "Category" else "CAPEC_VIEW" if _local(element.tag) == "View" else "CAPEC",
                "name": element.attrib.get("Name", ""),
                "description": _text(next((child for child in element if _local(child.tag) in {"Description", "Summary"}), None)),
                "source": "CAPEC",
                "source_id": identifier,
                "version": "latest",
                "created_at": "",
                "updated_at": "",
                "references": refs,
                "metadata": {"relationships": [{"nature": child.attrib.get("Nature", ""), "target": child.attrib.get("CAPEC_ID", "")} for child in element.iter() if _local(child.tag) in {"Related_Attack_Pattern", "Related_Weakness"}]},
            })
        count = write_jsonl(normalized, rows)
        upsert_manifest(source_record(source="CAPEC", url=URL, path=raw, version="latest", records=count, license_name=LICENSE))
        record_artifact("normalized_capec", normalized, records=count)
        return {"source": "CAPEC", "records": count, "status": "processed", "normalized": artifact_path(normalized)}
    except Exception as exc:
        record_error("CAPEC", str(exc), url=URL)
        return {"source": "CAPEC", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.force), indent=2))


if __name__ == "__main__":
    main()
