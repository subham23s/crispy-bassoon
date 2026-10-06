"""Scheduled official-source refresh worker for Compose or a service manager."""
from __future__ import annotations

import argparse
import json
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings
from app.services.source_refresh import run_refresh, SOURCES, RefreshBusy, write_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=86400)
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--cached", action="store_true", help="Reprocess cached downloads instead of fetching current sources")
    args = parser.parse_args()
    if args.interval < 60:
        parser.error("interval must be at least 60 seconds")
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    state = {}
    while not stop.is_set():
        try:
            result = run_refresh(args.sources, force=not args.cached)
            state = {"status": "failed" if result["status"] == "failed" else "degraded" if result["failures"] else "ready", "last_run": datetime.now(timezone.utc).isoformat(), "interval_seconds": args.interval, "failures": len(result["failures"]), "sources": args.sources or list(SOURCES), "fresh_download_requested": not args.cached}
        except RefreshBusy:
            state = {"status": "busy", "last_run": datetime.now(timezone.utc).isoformat(), "interval_seconds": args.interval}
        except Exception as exc:
            state = {"status": "failed", "last_run": datetime.now(timezone.utc).isoformat(), "error": f"{type(exc).__name__}: {exc}"}
        state["once"] = args.once
        output = settings.data_dir / "processed/refresh_worker_status.json"
        write_status(output, state)
        print(json.dumps(state), flush=True)
        if args.once:
            raise SystemExit(0 if state["status"] == "ready" else 2)
        stop.wait(args.interval)
    state.update({"status": "stopped", "stopped_at": datetime.now(timezone.utc).isoformat(), "once": False})
    write_status(settings.data_dir / "processed/refresh_worker_status.json", state)
    print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
