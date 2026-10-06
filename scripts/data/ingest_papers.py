"""Acquire research-paper metadata from OpenAlex; optional open-access PDFs only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from common import DATA_DIR, fetch_bytes, ensure_data_dirs, record_artifact, record_error, source_record, upsert_manifest, write_json, write_jsonl

OPENALEX = "https://api.openalex.org/works"
LICENSE = "OpenAlex metadata API; individual works retain their own licenses. No paywall bypass."


def _abstract(work: dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not isinstance(inverted, dict):
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted.items():
        for position in positions or []:
            words[int(position)] = word
    return " ".join(words[index] for index in sorted(words))


def _record(work: dict[str, Any]) -> dict[str, Any]:
    authors = [item.get("author", {}).get("display_name", "") for item in work.get("authorships", []) or []]
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    return {
        "id": work.get("id", "").rsplit("/", 1)[-1],
        "entity_type": "RESEARCH_PAPER",
        "name": work.get("title", ""),
        "description": _abstract(work),
        "source": "OpenAlex",
        "source_id": work.get("id", ""),
        "version": "API",
        "created_at": work.get("publication_date", ""),
        "updated_at": work.get("publication_date", ""),
        "references": [{"url": work.get("doi", "") or work.get("id", "")}],
        "metadata": {
            "authors": authors,
            "year": work.get("publication_year"),
            "doi": work.get("doi", ""),
            "venue": source.get("display_name", ""),
            "keywords": [item.get("display_name", "") for item in work.get("keywords", []) or []],
            "open_access": work.get("open_access", {}),
            "landing_page_url": primary.get("landing_page_url", ""),
            "pdf_url": (primary.get("pdf_url") or ""),
            "license": (work.get("open_access") or {}).get("oa_url", ""),
        },
    }


def ingest(query: str = "cybersecurity", per_page: int = 25, full_text: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    raw = DATA_DIR / "raw/papers/openalex.json"
    normalized = DATA_DIR / "normalized/research_papers.jsonl"
    try:
        params = urlencode({"search": query, "per-page": min(per_page, 100), "mailto": os.getenv("OPENALEX_MAILTO", "")})
        payload = fetch_bytes(f"{OPENALEX}?{params}", timeout=30)
        raw.write_bytes(payload)
        data = json.loads(payload)
        rows = [_record(work) for work in data.get("results", []) if isinstance(work, dict) and work.get("title")]
        count = write_jsonl(normalized, rows)
        if full_text:
            pdf_dir = DATA_DIR / "raw/papers/pdf"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            for row in rows:
                pdf_url = row["metadata"].get("pdf_url")
                if not pdf_url or not str(pdf_url).startswith("http"):
                    continue
                try:
                    pdf = fetch_bytes(str(pdf_url), timeout=30, retries=2)
                    (pdf_dir / f"{row['id']}.pdf").write_bytes(pdf)
                except Exception as exc:
                    record_error("OpenAlex PDF", str(exc), url=str(pdf_url))
        upsert_manifest(source_record(source="OpenAlex", url=OPENALEX, path=raw, version="API", records=count, license_name=LICENSE, extra={"query": query, "full_text_requested": full_text}))
        record_artifact("normalized_research_papers", normalized, records=count)
        return {"source": "OpenAlex", "records": count, "status": "processed", "full_text_requested": full_text}
    except Exception as exc:
        record_error("OpenAlex", str(exc), url=OPENALEX)
        return {"source": "OpenAlex", "records": 0, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="cybersecurity")
    parser.add_argument("--per-page", type=int, default=25)
    parser.add_argument("--full-text", action="store_true", help="download only openly advertised PDF URLs; verify licenses yourself")
    args = parser.parse_args()
    print(json.dumps(ingest(args.query, args.per_page, args.full_text), indent=2))


if __name__ == "__main__":
    main()
