"""Download and normalize the latest official CWE XML archive."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from common import DATA_DIR, artifact_path, download_to, ensure_data_dirs, record_artifact, record_error, source_record, upsert_manifest, write_jsonl

URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
LICENSE = "CWE data; subject to MITRE CWE terms of use."


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(element: ET.Element | None) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def ingest(force: bool = False) -> dict[str, object]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/cwe/cwe_latest.xml.zip"
    normalized = DATA_DIR / "normalized/cwe.jsonl"
    try:
        download_to(URL, raw, source="CWE", version="latest", license_name=LICENSE, force=force)
        rows = []
        with zipfile.ZipFile(raw) as archive:
            xml_name = next((name for name in archive.namelist() if name.lower().endswith(".xml")), None)
            if not xml_name:
                raise RuntimeError("CWE archive did not contain XML")
            root = ET.fromstring(archive.read(xml_name))
        for element in root.iter():
            tag = _local(element.tag)
            if tag not in {"Weakness", "Category", "View"}:
                continue
            identifier = element.attrib.get("ID", "")
            if not identifier:
                continue
            refs = []
            for ref in element.iter():
                if _local(ref.tag) in {"Reference", "External_Reference"}:
                    refs.append({"id": ref.attrib.get("Reference_ID", ""), "url": ref.attrib.get("URL", "")})
            rows.append({
                "id": f"CWE-{identifier}" if not identifier.startswith("CWE-") else identifier,
                "entity_type": "CWE_CATEGORY" if tag == "Category" else "CWE_VIEW" if tag == "View" else "CWE",
                "name": element.attrib.get("Name", ""),
                "description": _text(next((child for child in element if _local(child.tag) in {"Description", "Extended_Description"}), None)),
                "source": "CWE",
                "source_id": identifier,
                "version": "latest",
                "created_at": "",
                "updated_at": "",
                "references": refs,
                "metadata": {"status": element.attrib.get("Status", ""), "relationships": [{"nature": child.attrib.get("Nature", ""), "cwe_id": child.attrib.get("CWE_ID", "")} for child in element.iter() if _local(child.tag) == "Related_Weakness" ]},
            })
        count = write_jsonl(normalized, rows)
        upsert_manifest(source_record(source="CWE", url=URL, path=raw, version="latest", records=count, license_name=LICENSE))
        record_artifact("normalized_cwe", normalized, records=count)
        return {"source": "CWE", "records": count, "status": "processed", "normalized": artifact_path(normalized)}
    except Exception as exc:
        record_error("CWE", str(exc), url=URL)
        return {"source": "CWE", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.force), indent=2))


if __name__ == "__main__":
    main()
