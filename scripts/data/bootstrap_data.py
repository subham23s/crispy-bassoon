"""Build the data/ tree from an empty directory through reproducible stages."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import ROOT, DATA_DIR, ensure_data_dirs, hardware_profile, read_manifest, record_artifact, utc_now, write_json


SCRIPT_DIR = Path(__file__).resolve().parent


def _run(script: str, *args: str) -> dict[str, Any]:
    script_path = ROOT / script if "/" in script else SCRIPT_DIR / script
    command = [sys.executable, str(script_path), *args]
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, "DATA_DIR": str(DATA_DIR), "PYTHONPATH": str(ROOT / "backend")}, capture_output=True, text=True, check=False)
    stdout = result.stdout.strip()
    parsed: dict[str, Any] = {"script": script, "status": "error", "returncode": result.returncode, "stderr": result.stderr[-1000:]}
    candidates = [stdout] + list(reversed(stdout.splitlines()))
    result_value = None
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                result_value = value
                parsed.update(value)
                break
        except json.JSONDecodeError:
            continue
    if result.returncode != 0:
        parsed["status"] = "error"
    elif result_value is not None:
        # A tool can report a real acquisition failure while exiting normally.
        parsed["status"] = result_value.get("status", "processed")
    return parsed


def _processing() -> list[dict[str, Any]]:
    return [
        _run("process_papers.py"),
        _run("normalize_data.py"),
        _run("build_chunks.py"),
        _run("build_embeddings.py"),
        _run("build_vector_index.py"),
        _run("build_bm25.py"),
        _run("build_graph.py"),
        _run("build_ml_datasets.py"),
        _run("scripts/validate_datasets.py"),
        _run("scripts/data/validate_bootstrap.py"),
    ]


def bootstrap(*, minimal: bool = False, full: bool = False, evaluation: bool = False, papers: bool = False, full_text: bool = False, train_baselines: bool = False, update: bool = False, force: bool = False) -> dict[str, Any]:
    ensure_data_dirs()
    report: dict[str, Any] = {"started_at": utc_now(), "hardware": hardware_profile(), "mode": "full" if full else "minimal" if minimal else "evaluation" if evaluation else "custom", "sources": [], "processing": [], "warnings": []}
    if evaluation:
        report["processing"].append(_run("build_ml_datasets.py"))
        report["processing"].append(_run("scripts/validate_datasets.py"))
    else:
        sources = ["ingest_mitre_attack.py", "ingest_cisa_kev.py", "ingest_nvd.py", "ingest_nist.py", "ingest_cisa_advisories.py", "ingest_owasp.py", "ingest_tools.py"]
        if full:
            sources.extend(["ingest_mitre_atlas.py", "ingest_cwe.py", "ingest_capec.py"])
        if papers:
            sources.append("ingest_papers.py")
        for script in sources:
            args: list[str] = []
            if force and script not in {"ingest_nvd.py", "ingest_papers.py"}:
                args.append("--force")
            if script == "ingest_nvd.py" and update:
                args.append("--update")
            if script == "ingest_papers.py" and full_text:
                args.append("--full-text")
            result = _run(script, *args)
            report["sources"].append(result)
        report["processing"].extend(_processing())
        if train_baselines:
            report["processing"].extend([_run("scripts/train_intent.py"), _run("scripts/train_ood.py"), _run("scripts/evaluate_models.py")])
    manifest = read_manifest()
    report["finished_at"] = utc_now()
    report["manifest"] = {"sources": len(manifest.get("sources", [])), "artifacts": len(manifest.get("artifacts", [])), "errors": len(manifest.get("errors", []))}
    report["errors"] = [item for item in report["sources"] + report["processing"] if item.get("status") in {"error", "partial", "invalid", "blocked"} or item.get("failures") or item.get("returncode", 0) != 0]
    report["warnings"].extend(["External sources are only represented as downloaded when a real fetch succeeded.", "Synthetic ML rows are marked synthetic=true and are not authoritative cybersecurity intelligence.", "Transformer embeddings, pgvector, Redis, and Neo4j are not silently installed or claimed; the local embedding/index artifacts are explicit baselines."])
    report_path = DATA_DIR / "processed/bootstrap_report.json"
    write_json(report_path, report)
    write_json(DATA_DIR / "data_version.json", {"schema_version": "1.0", "processing_version": "cybersecra-x-bootstrap-0.1", "generated_at": report["finished_at"], "hardware_profile": report["hardware"], "source_manifest": "data/data_manifest.json", "sources": [{"source": item.get("source"), "version": item.get("version"), "checksum": item.get("checksum"), "status": item.get("status")} for item in manifest.get("sources", [])], "embedding_model": "tfidf-lite", "notes": report["warnings"]})
    record_artifact("bootstrap_report", report_path, records=len(report["sources"]) + len(report["processing"]))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CyberSecRA-X data with official-source provenance.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--minimal", action="store_true", help="bounded laptop profile: core public sources and recent NVD window")
    group.add_argument("--full", action="store_true", help="all configured structured sources")
    group.add_argument("--evaluation", action="store_true", help="only build evaluation and ML datasets")
    parser.add_argument("--papers", action="store_true", help="also acquire OpenAlex metadata")
    parser.add_argument("--full-text", action="store_true", help="download only openly advertised paper PDFs when --papers is selected")
    parser.add_argument("--train-baselines", action="store_true", help="train/evaluate the reproducible CPU intent and OOD baselines")
    parser.add_argument("--update", action="store_true", help="use incremental NVD last-modified state")
    parser.add_argument("--force", action="store_true", help="redownload raw source files")
    args = parser.parse_args()
    report = bootstrap(minimal=args.minimal, full=args.full, evaluation=args.evaluation, papers=args.papers or args.full, full_text=args.full_text, train_baselines=args.train_baselines, update=args.update, force=args.force)
    print("=" * 49)
    print("CYBERSEC-RA-X DATA BOOTSTRAP REPORT")
    print("=" * 49)
    print(json.dumps({"mode": report["mode"], "sources": report["sources"], "processing": report["processing"], "manifest": report["manifest"], "errors": report["errors"], "warnings": report["warnings"], "last_update": report["finished_at"]}, indent=2))
    print("=" * 49)
    if report["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
