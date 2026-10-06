"""Bounded background document processing with explicit lifecycle states."""
from __future__ import annotations

import threading
import uuid
import json
import logging
from pathlib import Path
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DocumentJobManager:
    STATES = {"QUEUED", "PROCESSING", "COMPLETED", "FAILED"}

    def __init__(self, worker: Callable[..., Any], *, max_workers: int = 2, max_pending: int = 32, spool_dir: Path | None = None, on_update: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.worker = worker
        self.on_update = on_update
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cybersecra-ingest")
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(max_pending)
        self.spool_dir = spool_dir
        if spool_dir:
            spool_dir.mkdir(parents=True, exist_ok=True)
            self._recover()

    def submit(self, *, filename: str, payload: bytes, owner_id: str, source: str = "user_upload", source_type: str = "user_document") -> dict[str, Any]:
        if not self.slots.acquire(blocking=False):
            raise ValueError("Document processing queue is full; retry after pending jobs finish")
        job_id = f"job-{uuid.uuid4()}"
        record = {"job_id": job_id, "status": "QUEUED", "filename": filename, "owner_id": owner_id, "source": source, "source_type": source_type, "submitted_at": _now(), "started_at": None, "finished_at": None, "document_id": None, "error": None}
        with self.lock:
            self.jobs[job_id] = record
        try:
            if self.spool_dir:
                temporary = self.spool_dir / f"{job_id}.bin.tmp"
                temporary.write_bytes(payload)
                temporary.replace(self.spool_dir / f"{job_id}.bin")
            self._emit(record)
            future = self.executor.submit(self._run, job_id, filename, payload, owner_id, source, source_type)
        except Exception:
            self.slots.release()
            with self.lock:
                self.jobs.pop(job_id, None)
            raise
        future.add_done_callback(lambda result: self._future_error(job_id, result))
        return dict(record)

    def _recover(self) -> None:
        """Resume accepted uploads after a process restart; inputs are durable."""
        for path in sorted(self.spool_dir.glob("job-*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                job_id = record["job_id"]
                if path.stem != job_id or not record.get("owner_id"):
                    continue
                self.jobs[job_id] = record
                if record["status"] in {"QUEUED", "PROCESSING"}:
                    payload_path = self.spool_dir / f"{job_id}.bin"
                    if not payload_path.exists():
                        record.update(status="FAILED", error="Interrupted job has no durable input; upload again", finished_at=_now())
                        self._emit(record)
                        continue
                    # Recovery submits at most the bounded number of accepted
                    # jobs; overflow stays explicitly failed rather than hidden.
                    if not self.slots.acquire(blocking=False):
                        record.update(status="FAILED", error="Recovery queue capacity exceeded; upload again", finished_at=_now())
                        self._emit(record)
                        continue
                    record["status"] = "QUEUED"
                    future = self.executor.submit(self._run, job_id, record["filename"], payload_path.read_bytes(), record["owner_id"], record.get("source", "user_upload"), record.get("source_type", "user_document"))
                    future.add_done_callback(lambda result, key=job_id: self._future_error(key, result))
            except (OSError, ValueError, KeyError):
                logging.getLogger(__name__).exception("Cannot recover ingestion job %s", path.name)

    def _run(self, job_id: str, filename: str, payload: bytes, owner_id: str, source: str, source_type: str) -> None:
        with self.lock:
            self.jobs[job_id].update({"status": "PROCESSING", "started_at": _now()})
            record = dict(self.jobs[job_id])
        self._emit(record)
        try:
            document = self.worker(filename, payload, source=source, source_type=source_type, owner_id=owner_id)
            with self.lock:
                self.jobs[job_id].update({"status": "COMPLETED", "finished_at": _now(), "document_id": document.document_id, "document_status": "quarantined" if getattr(document, "security_flags", []) else "indexed"})
                record = dict(self.jobs[job_id])
            self._emit(record)
        except Exception as exc:
            with self.lock:
                self.jobs[job_id].update({"status": "FAILED", "finished_at": _now(), "error": f"{type(exc).__name__}: {exc}"})
                record = dict(self.jobs[job_id])
            self._emit(record)

    def _emit(self, record: dict[str, Any]) -> None:
        if self.spool_dir:
            with self.lock:
                temporary = self.spool_dir / f"{record['job_id']}.json.tmp"
                temporary.write_text(json.dumps(record), encoding="utf-8")
                temporary.replace(self.spool_dir / f"{record['job_id']}.json")
        if self.on_update is not None:
            try:
                self.on_update(dict(record))
            except Exception:
                logging.getLogger(__name__).exception("Repository update failed for ingestion job %s", record["job_id"])

    def _future_error(self, job_id: str, future: Future[Any]) -> None:
        try:
            future.result()
        except Exception as exc:
            with self.lock:
                if self.jobs.get(job_id, {}).get("status") not in {"COMPLETED", "FAILED"}:
                    self.jobs[job_id].update({"status": "FAILED", "finished_at": _now(), "error": f"{type(exc).__name__}: {exc}"})
                    self._emit(self.jobs[job_id])
        finally:
            self.slots.release()
            if self.spool_dir and self.jobs.get(job_id, {}).get("status") in {"COMPLETED", "FAILED"}:
                (self.spool_dir / f"{job_id}.bin").unlink(missing_ok=True)

    def get(self, job_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.lock:
            record = self.jobs.get(job_id)
            if not record or record.get("owner_id") != owner_id:
                return None
            return dict(record)

    def list(self, owner_id: str) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(item) for item in sorted(self.jobs.values(), key=lambda value: value["submitted_at"], reverse=True) if item.get("owner_id") == owner_id]

    def close(self) -> None:
        self.executor.shutdown(wait=True)
