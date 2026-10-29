"""Incrementally ingest NVD CVE data through the permitted API v2.0.

By default this is deliberately bounded to a recent seven-day window. Use
`--cve` for one record or explicit date ranges; no whole-corpus download occurs
unless the operator explicitly requests a broad range and page limit.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from common import DATA_DIR, fetch_bytes, ensure_data_dirs, load_json, record_artifact, record_error, source_record, upsert_manifest, utc_now, write_json, write_jsonl, read_jsonl

BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
LICENSE = "NVD data/API; follow NVD API terms, rate limits, and attribution guidance."


def _api_date(value: str, *, end_of_day: bool = False) -> str:
    raw = value.strip()
    if len(raw) == 10:
        raw += "T23:59:59" if end_of_day else "T00:00:00"
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _record(wrapper: dict[str, Any]) -> dict[str, Any]:
    cve = wrapper.get("cve", wrapper)
    cve_id = cve.get("id", "")
    descriptions = cve.get("descriptions", []) or []
    description = next((item.get("value", "") for item in descriptions if item.get("lang") == "en"), descriptions[0].get("value", "") if descriptions else "")
    metrics = cve.get("metrics", {}) or {}
    cvss = None
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if metrics.get(key):
            entry = metrics[key][0]
            cvss = entry.get("cvssData", {})
            break
    weaknesses = []
    for weakness in cve.get("weaknesses", []) or []:
        for desc in weakness.get("description", []) or []:
            if desc.get("value"):
                weaknesses.append(desc["value"])
    references = [{"url": ref.get("url", ""), "source": ref.get("source", ""), "tags": ref.get("tags", [])} for ref in cve.get("references", []) or []]
    products = []
    for node in (cve.get("configurations", []) or []):
        for config_node in node.get("nodes", []) if isinstance(node, dict) else []:
            for match in config_node.get("cpeMatch", []) or []:
                products.append({"criteria": match.get("criteria", ""), "versionStartIncluding": match.get("versionStartIncluding"), "versionEndExcluding": match.get("versionEndExcluding"), "vulnerable": match.get("vulnerable")})
    return {
        "id": cve_id,
        "entity_type": "CVE",
        "name": cve_id,
        "description": description,
        "source": "NVD",
        "source_id": cve_id,
        "version": cve.get("vulnStatus", ""),
        "created_at": cve.get("published", ""),
        "updated_at": cve.get("lastModified", ""),
        "references": references,
        "metadata": {"cvss": cvss, "weaknesses": weaknesses, "products": products, "sourceIdentifier": cve.get("sourceIdentifier", ""), "vulnStatus": cve.get("vulnStatus", "")},
    }


def _load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def ingest(*, cve_id: str | None = None, start_date: str | None = None, end_date: str | None = None, update: bool = False, limit: int = 2000, max_pages: int = 5, api_key: str = "") -> dict[str, Any]:
    ensure_data_dirs()
    raw_dir = DATA_DIR / "raw/nvd"
    normalized = DATA_DIR / "normalized/nvd.jsonl"
    state_path = raw_dir / "state.json"
    state = _load_state(state_path)
    pending = state.get("pending_update") if update and not cve_id and not start_date and not end_date else None
    if pending:
        start_date, end_date = pending["start_date"], pending["end_date"]
    elif update and not start_date:
        start_date = state.get("last_modified_start")
    if not cve_id and not start_date:
        start_date = (datetime.now(timezone.utc) - timedelta(days=7)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if start_date:
        start_date = _api_date(start_date)
    if not end_date:
        end_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    end_date = _api_date(end_date, end_of_day=True)
    headers = {"apiKey": api_key} if api_key else {}
    records_by_id = {row.get("id"): row for row in read_jsonl(normalized) if row.get("id")}
    downloaded = 0
    page_size = min(max(1, limit), 2000)
    page_budget = min(max(1, max_pages), 20)
    configured_delay = os.getenv("NVD_REQUEST_DELAY_SECONDS", "").strip()
    request_delay = max(0.0, float(configured_delay or ("0.6" if api_key else "6")))
    start_index = int(pending["next_start_index"]) if pending else 0
    complete = False
    raw_paths = []
    try:
        for page in range(page_budget):
            if page and request_delay:
                time.sleep(request_delay)
            params: dict[str, str | int] = {"resultsPerPage": page_size, "startIndex": start_index}
            if cve_id:
                params["cveId"] = cve_id
            else:
                if start_date:
                    params["lastModStartDate" if update else "pubStartDate"] = start_date
                if end_date:
                    params["lastModEndDate" if update else "pubEndDate"] = end_date
            url = f"{BASE_URL}?{urlencode(params)}"
            raw = fetch_bytes(url, headers=headers, timeout=45, retries=3, min_delay=max(1.0, request_delay))
            downloaded += 1
            payload = json.loads(raw)
            raw_path = raw_dir / f"response-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{page}.json"
            write_json(raw_path, payload)
            raw_paths.append(raw_path)
            for wrapper in payload.get("vulnerabilities", []) or []:
                row = _record(wrapper)
                if row["id"]:
                    records_by_id[row["id"]] = row
            total = int(payload.get("totalResults", len(payload.get("vulnerabilities", []) or [])))
            returned = len(payload.get("vulnerabilities", []) or [])
            start_index += returned
            complete = bool(cve_id) or start_index >= total
            if complete:
                break
            if returned == 0:
                raise RuntimeError("NVD returned an empty page before totalResults was reached")
        rows = sorted(records_by_id.values(), key=lambda row: row.get("id", ""))
        count = write_jsonl(normalized, rows)
        state["last_ingestion"] = utc_now()
        if update and not cve_id:
            if complete:
                # Resume from the completed window boundary, never from wall
                # time after a truncated or slow multi-page download.
                state["last_modified_start"] = end_date
                state.pop("pending_update", None)
            else:
                state["pending_update"] = {"start_date": start_date, "end_date": end_date, "next_start_index": start_index}
        write_json(state_path, state)
        result_status = "processed" if complete else "partial"
        upsert_manifest(source_record(source="NVD", url=BASE_URL, path=raw_paths[0] if raw_paths else normalized, version="API v2.0", records=count, license_name=LICENSE, status=result_status, extra={"query": {"cve": cve_id, "start_date": start_date, "end_date": end_date, "update": update}, "pages_downloaded": downloaded, "complete": complete, "next_start_index": None if complete else start_index}))
        record_artifact("normalized_nvd", normalized, records=count)
        return {"source": "NVD", "records": count, "downloaded_pages": downloaded, "query": {"cve": cve_id, "start_date": start_date, "end_date": end_date, "update": update}, "status": result_status, "complete": complete, "next_start_index": None if complete else start_index, "failures": [] if complete else [{"error": "NVD page budget reached before all matching records were fetched", "resumable": update and not cve_id}]}
    except Exception as exc:
        record_error("NVD", str(exc), url=BASE_URL)
        return {"source": "NVD", "records": len(records_by_id), "downloaded_pages": downloaded, "status": "error", "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cve")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--limit", type=int, default=int(os.getenv("NVD_RESULTS_PER_PAGE", "2000")), help="Results requested per NVD API page (maximum 2000).")
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("NVD_MAX_PAGES", "5")), help="Maximum pages to fetch in one run; larger values take longer and must respect NVD rate limits.")
    parser.add_argument("--api-key", default=os.getenv("NVD_API_KEY", ""))
    args = parser.parse_args()
    print(json.dumps(ingest(cve_id=args.cve, start_date=args.start_date, end_date=args.end_date, update=args.update, limit=args.limit, max_pages=args.max_pages, api_key=args.api_key), indent=2))


if __name__ == "__main__":
    main()
