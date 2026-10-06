"""Fetch a small, explicitly configured set of official reference pages.

This is not a crawler. Operators edit data/source_config.json and each listed
URL is fetched at most once per run, with source/terms metadata preserved.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from common import ROOT, DATA_DIR, artifact_path, download_to, ensure_data_dirs, load_json, record_artifact, record_error, source_record, upsert_manifest, write_jsonl


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            value = html.unescape(data).strip()
            if value:
                self.parts.append(value)


def _extract(raw: bytes) -> str:
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parser.parts))


def ingest(source_key: str, source_name: str, directory: str, force: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    config_path = DATA_DIR / "source_config.json"
    config = load_json(config_path if config_path.exists() else ROOT / "data/source_config.json").get(source_key, [])
    normalized = DATA_DIR / f"normalized/{source_key}_pages.jsonl"
    rows = []
    failures = []
    for index, item in enumerate(config):
        title, url = str(item.get("title", "")), str(item.get("url", ""))
        raw_path = DATA_DIR / "raw" / directory / f"page-{index + 1}.html"
        try:
            download_to(url, raw_path, source=source_name, version="configured-page", license_name=str(item.get("license", "verify source terms")), force=force)
            text = _extract(raw_path.read_bytes())
            rows.append({
                "id": f"{source_key}-page-{index + 1}",
                "entity_type": "DOCUMENT",
                "name": title,
                "description": text,
                "source": source_name,
                "source_id": url,
                "version": "configured-page",
                "created_at": "",
                "updated_at": "",
                "references": [{"url": url}],
                "metadata": {"title": title, "url": url, "license": item.get("license", "")},
            })
        except Exception as exc:
            failures.append({"title": title, "url": url, "error": str(exc)})
            record_error(source_name, str(exc), url=url)
    count = write_jsonl(normalized, rows)
    status = "processed" if rows else "error"
    upsert_manifest({"source": source_name, "version": "configured-pages", "downloaded_at": None, "processed_at": datetime.now(timezone.utc).isoformat(), "records": count, "license": "per-page terms in data/source_config.json", "url": "data/source_config.json", "checksum": "", "status": status, "failures": failures})
    record_artifact(f"normalized_{source_key}_pages", normalized, records=count)
    return {"source": source_name, "records": count, "failures": failures, "status": status, "normalized": artifact_path(normalized)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=("nist", "owasp"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(args.source, "NIST" if args.source == "nist" else "OWASP", args.source, args.force), indent=2))


if __name__ == "__main__":
    main()
