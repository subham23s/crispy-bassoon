"""Optional in-process scheduler wrapper; production can replace runner with Celery."""
from __future__ import annotations

import threading
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from app.services.source_refresh import SOURCES, run_refresh


@dataclass
class RefreshManager:
    """Start bounded refresh jobs and expose actual lifecycle state."""
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cybersecra-refresh")
        self.lock = threading.RLock()
        self.jobs: dict[str, dict[str, Any]] = {}

    def start(self, sources: list[str] | None = None, force: bool = False) -> dict[str, Any]:
        if sources is not None and (not sources or any(name not in SOURCES for name in sources)):
            raise ValueError("Unknown or empty refresh source selection")
        job_id = f"refresh-{uuid.uuid4()}"
        record = {"job_id": job_id, "status": "QUEUED", "sources": sources or [], "force": force, "submitted_at": datetime.now(timezone.utc).isoformat(), "result": None, "error": None}
        with self.lock:
            if any(job["status"] in {"QUEUED", "PROCESSING"} for job in self.jobs.values()):
                raise ValueError("A source refresh is already active")
            self.jobs[job_id] = record
            self.executor.submit(self._run, job_id, sources, force)
        return dict(record)

    def _run(self, job_id: str, sources: list[str] | None, force: bool) -> None:
        with self.lock: self.jobs[job_id].update({"status": "PROCESSING", "started_at": datetime.now(timezone.utc).isoformat()})
        try:
            result = run_refresh(sources, force=force)
            state = "FAILED" if result.get("status") == "failed" else "PARTIAL" if result.get("failures") else "COMPLETED"
            with self.lock: self.jobs[job_id].update({"status": state, "finished_at": datetime.now(timezone.utc).isoformat(), "result": result})
        except Exception as exc:
            with self.lock: self.jobs[job_id].update({"status": "FAILED", "finished_at": datetime.now(timezone.utc).isoformat(), "error": f"{type(exc).__name__}: {exc}"})

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock: return dict(self.jobs[job_id]) if job_id in self.jobs else None

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(value) for value in self.jobs.values()]


@dataclass
class RefreshScheduler:
    interval_seconds: int = 86_400
    sources: list[str] | None = None

    def __post_init__(self) -> None:
        self._timer: threading.Timer | None = None
        self._stopped = False

    def run_once(self) -> dict[str, Any]:
        return run_refresh(self.sources, force=True)

    def _tick(self) -> None:
        if self._stopped:
            return
        try:
            self.run_once()
        except Exception:
            logging.getLogger(__name__).exception("Scheduled source refresh failed")
        finally:
            if not self._stopped:
                self._timer = threading.Timer(self.interval_seconds, self._tick)
                self._timer.daemon = True
                self._timer.start()

    def start(self) -> None:
        if self._timer is None:
            if self.interval_seconds < 60:
                raise ValueError("Refresh interval must be at least 60 seconds")
            self._stopped = False
            self._timer = threading.Timer(0, self._tick)
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        if self._timer:
            self._timer.cancel()
            self._timer = None
