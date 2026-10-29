"""Bounded source refresh job abstraction used by CLI/schedulers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR, settings

SOURCES = {
    "mitre_attack": "scripts/data/ingest_mitre_attack.py",
    "mitre_atlas": "scripts/data/ingest_mitre_atlas.py",
    "cisa_kev": "scripts/data/ingest_cisa_kev.py",
    "nvd": "scripts/data/ingest_nvd.py",
    "cwe": "scripts/data/ingest_cwe.py",
    "capec": "scripts/data/ingest_capec.py",
    "nist": "scripts/data/ingest_nist.py",
    "tools": "scripts/data/ingest_tools.py",
    "cisa_advisories": "scripts/data/ingest_cisa_advisories.py",
    "owasp": "scripts/data/ingest_owasp.py",
}


class RefreshBusy(RuntimeError):
    """Another process is already publishing source artifacts."""


@contextmanager
def refresh_lock():
    # A transaction lock is released by the OS even after a worker crash. It
    # coordinates API workers and the standalone scheduler sharing DATA_DIR.
    directory = settings.data_dir / "processed"
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "refresh_lock.sqlite", timeout=0)
    try:
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise RefreshBusy("A source refresh is already active") from exc
            raise
        yield
    finally:
        connection.close()


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _last_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    for candidate in [text, *reversed(text.splitlines())]:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    # Tools may log progress before a pretty-printed JSON object.
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[offset:])
            if isinstance(value, dict) and not text[offset + end:].strip():
                return value
        except json.JSONDecodeError:
            continue
    return {}


def run_refresh(selected: list[str] | None = None, *, update_nvd: bool = True, force: bool = False) -> dict[str, Any]:
    if selected is not None and (not selected or any(name not in SOURCES for name in selected)):
        raise ValueError("Unknown or empty refresh source selection")
    with refresh_lock():
        return _run_refresh(selected, update_nvd=update_nvd, force=force)


def _run_refresh(selected: list[str] | None, *, update_nvd: bool, force: bool) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    names = list(dict.fromkeys(selected or SOURCES))
    environment = {**os.environ, "DATA_DIR": str(settings.data_dir.resolve()), "PYTHONPATH": str(ROOT_DIR / "backend")}
    results = []
    for name in names:
        if name not in SOURCES:
            results.append({"source": name, "status": "error", "error": "unknown configured source"})
            continue
        command = [sys.executable, str(ROOT_DIR / SOURCES[name])]
        if force and name != "nvd":
            command.append("--force")
        if name == "nvd" and update_nvd:
            command.append("--update")
        try:
            completed = subprocess.run(command, cwd=ROOT_DIR, env=environment, capture_output=True, text=True, check=False, timeout=900)
        except (subprocess.TimeoutExpired, OSError) as exc:
            results.append({"source_key": name, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            continue
        result = _last_json(completed.stdout)
        if not result or result.get("status") not in {"processed", "error", "partial"}:
            result = {"status": "error", "error": "Source did not return a recognized JSON result"}
        if result.get("failures") and result.get("status") != "error":
            result["status"] = "partial"
        result.update({"source_key": name, "returncode": completed.returncode, "stderr": completed.stderr[-1000:]})
        if completed.returncode != 0:
            result["status"] = "error"
        results.append(result)
    processing = []
    if any(item.get("returncode") == 0 and item.get("status") != "error" for item in results):
        for script in ("normalize_data.py", "build_chunks.py", "build_embeddings.py", "build_vector_index.py", "build_bm25.py", "build_graph.py"):
            try:
                completed = subprocess.run([sys.executable, str(ROOT_DIR / "scripts/data" / script)], cwd=ROOT_DIR, env=environment, capture_output=True, text=True, check=False, timeout=900)
                result = _last_json(completed.stdout)
                processed = completed.returncode == 0 and bool(result) and result.get("status") not in {"error", "invalid", "blocked", "partial"}
                processing.append({"script": script, "status": "processed" if processed else "error", "returncode": completed.returncode, "result": result, "stderr": completed.stderr[-1000:]})
            except (subprocess.TimeoutExpired, OSError) as exc:
                processing.append({"script": script, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            if processing[-1]["status"] == "error":
                break
    status = {"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(), "force": force, "results": results, "processing": processing, "last_successful_update": [item.get("source_key") for item in results if item.get("status") == "processed"], "failures": [item for item in results + processing if item.get("status") in {"error", "partial"}]}
    status["status"] = "completed" if not status["failures"] else "partial" if any(item.get("returncode") == 0 and item.get("status") != "error" for item in results) else "failed"
    if any(item["status"] == "error" for item in processing):
        status["status"] = "failed"
        status["last_successful_update"] = []
    write_status(settings.data_dir / "processed" / "source_update_status.json", status)
    return status
