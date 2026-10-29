"""Shared, rate-limited, provenance-preserving data bootstrap helpers."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import _load_dotenv
_load_dotenv()
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
MANIFEST_PATH = DATA_DIR / "data_manifest.json"


def artifact_path(path: Path) -> str:
    """Retain repository-relative provenance, or an explicit external path."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def checksum_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_data_dirs() -> None:
    for relative in (
        "raw/mitre", "raw/atlas", "raw/nvd", "raw/cisa", "raw/cisa_advisories", "raw/cwe", "raw/capec", "raw/nist", "raw/owasp", "raw/tools", "raw/papers",
        "processed", "normalized", "chunks", "embeddings", "graph", "ml/intent", "ml/ood", "ml/reranker", "ml/verification", "evaluation", "demo",
    ):
        (DATA_DIR / relative).mkdir(parents=True, exist_ok=True)


def read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"schema_version": "1.0", "updated_at": utc_now(), "sources": [], "artifacts": [], "errors": []}
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"schema_version": "1.0", "sources": [], "artifacts": [], "errors": []}
    except json.JSONDecodeError:
        return {"schema_version": "1.0", "updated_at": utc_now(), "sources": [], "artifacts": [], "errors": ["Existing manifest was invalid JSON and was replaced."]}


def write_manifest(manifest: dict[str, Any]) -> None:
    ensure_data_dirs()
    manifest["updated_at"] = utc_now()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def upsert_manifest(record: dict[str, Any]) -> None:
    manifest = read_manifest()
    sources = [item for item in manifest.get("sources", []) if item.get("source") != record.get("source")]
    sources.append(record)
    manifest["sources"] = sources
    write_manifest(manifest)


def record_artifact(name: str, path: Path, *, records: int | None = None, status: str = "processed", metadata: dict[str, Any] | None = None) -> None:
    manifest = read_manifest()
    artifacts = [item for item in manifest.get("artifacts", []) if item.get("name") != name]
    artifact = {
        "name": name,
        "path": artifact_path(path),
        "checksum": checksum_file(path) if path.exists() else "",
        "records": records,
        "status": status,
        "created_at": utc_now(),
    }
    if metadata:
        artifact.update(metadata)
    artifacts.append(artifact)
    manifest["artifacts"] = artifacts
    write_manifest(manifest)


def record_error(source: str, error: str, *, url: str = "") -> None:
    manifest = read_manifest()
    errors = manifest.setdefault("errors", [])
    errors.append({"source": source, "url": url, "error": error, "timestamp": utc_now()})
    write_manifest(manifest)


def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
    min_delay: float = 0.5,
) -> bytes:
    """Fetch an approved URL with bounded exponential backoff and a clear failure."""
    request_headers = {
        "User-Agent": "CyberSecRA-X-data-bootstrap/0.1 (+https://github.com/; research use; respect source terms)",
        "Accept": "application/json, application/yaml, application/xml, text/plain, */*",
    }
    request_headers.update(headers or {})
    last_error: Exception | None = None
    for attempt in range(retries):
        if attempt:
            time.sleep(min_delay * (2 ** (attempt - 1)))
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - URL is an explicit source configuration.
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in {401, 403, 404}:
                break
    raise RuntimeError(f"download failed after {retries} attempt(s): {url}: {last_error}")


def download_to(
    url: str,
    path: Path,
    *,
    source: str,
    version: str = "unknown",
    license_name: str = "verify source terms before redistribution",
    headers: dict[str, str] | None = None,
    force: bool = False,
) -> tuple[Path, bool]:
    ensure_data_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force and path.stat().st_size > 0:
        upsert_manifest({
            "source": source,
            "version": version,
            "downloaded_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
            "records": None,
            "license": license_name,
            "url": url,
            "checksum": checksum_file(path),
            "status": "raw_cached",
            "path": artifact_path(path),
        })
        return path, False
    payload = fetch_bytes(url, headers=headers)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(path)
    upsert_manifest({
        "source": source,
        "version": version,
        "downloaded_at": utc_now(),
        "records": None,
        "license": license_name,
        "url": url,
        "checksum": checksum_bytes(payload),
        "status": "downloaded",
        "path": artifact_path(path),
    })
    return path, True


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    temporary.replace(path)
    return count


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    def rows() -> Iterable[dict[str, Any]]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)
    return rows()


def source_record(*, source: str, url: str, path: Path, version: str, records: int, license_name: str, status: str = "processed", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source,
        "version": version,
        "downloaded_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat() if path.exists() else None,
        "processed_at": utc_now(),
        "records": records,
        "license": license_name,
        "url": url,
        "checksum": checksum_file(path) if path.exists() else "",
        "status": status,
        "path": artifact_path(path) if path.exists() else "",
    }
    if extra:
        record.update(extra)
    return record


def hardware_profile() -> dict[str, Any]:
    memory_bytes = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    except (FileNotFoundError, ValueError):
        pass
    gpu = None
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=5, check=False)
        if result.returncode == 0 and result.stdout.strip():
            gpu = result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    disk = shutil.disk_usage(DATA_DIR)
    return {
        "cpu_count": os.cpu_count() or 1,
        "ram_bytes": memory_bytes,
        "gpu": gpu,
        "storage_available_bytes": disk.free,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "recommended_profile": "gpu" if gpu else "low-resource-cpu",
    }


def safe_parse_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
