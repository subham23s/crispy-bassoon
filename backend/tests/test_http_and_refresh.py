import http.client
import json
import threading
import time
import unittest
import tempfile
import dataclasses
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main
from app.jobs.refresh import RefreshManager


class FallbackHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), main.FallbackHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_preflight_allows_real_client_operations_for_configured_origin(self):
        origin = main.settings.cors_origins[0]
        status, headers, _ = self.request("OPTIONS", "/experiments/fixture", headers={"Origin": origin})
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
        self.assertIn("DELETE", headers["Access-Control-Allow-Methods"])
        self.assertIn("PATCH", headers["Access-Control-Allow-Methods"])
        self.assertNotIn("Access-Control-Allow-Origin", self.request("OPTIONS", "/", headers={"Origin": "https://unconfigured.example"})[1])

    def test_malformed_and_oversized_bodies_are_rejected_before_dispatch(self):
        for body in (b'\xff', b'[]', b'{'):
            self.assertEqual(self.request("POST", "/chat/query", body)[0], 400)
        self.assertEqual(self.request("POST", "/chat/query", headers={"Content-Length": "-1"})[0], 400)
        self.assertEqual(self.request("POST", "/documents/upload", headers={"Content-Length": str(main.settings.max_upload_bytes * 2)})[0], 413)

    def test_stream_has_cors_and_fallback_passes_query_parameters(self):
        origin = main.settings.cors_origins[0]
        with patch.object(main, "_user_from_request", return_value={"sub": "fixture"}), patch.object(main, "_stream_query", return_value=iter(['event: complete\ndata: {"answer":{}}\n\n'])):
            status, headers, body = self.request("POST", "/chat/stream", b'{}', {"Origin": origin})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
        self.assertIn(b'event: complete', body)
        with patch.object(main, "_route", return_value=(200, {})) as route:
            self.request("GET", "/timeline?start=2024-02-26&end=2024-02-26")
        self.assertEqual(route.call_args.args[1], "/timeline?start=2024-02-26&end=2024-02-26")


class RefreshTests(unittest.TestCase):
    def test_partial_failures_and_duplicate_jobs_are_not_reported_as_success(self):
        manager = RefreshManager()
        release = threading.Event()
        def refresh(*args, **kwargs):
            release.wait(5)
            return {"status": "partial", "failures": [{"source": "nvd", "status": "error"}]}
        try:
            with patch("app.jobs.refresh.run_refresh", side_effect=refresh):
                job = manager.start(["nvd"])
                with self.assertRaises(ValueError):
                    manager.start(["nvd"])
                release.set()
                for _ in range(100):
                    current = manager.get(job["job_id"])
                    if current["status"] not in {"QUEUED", "PROCESSING"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(current["status"], "PARTIAL")
                self.assertTrue(current["result"]["failures"])
        finally:
            release.set()
            manager.executor.shutdown(wait=True)

    def test_admin_authorization_is_forbidden_not_session_expiration(self):
        with patch.object(main, "_user_from_request", return_value={"sub": "fixture", "role": "USER"}):
            self.assertEqual(main._route("GET", "/admin/overview", {}, {})[0], 403)
            self.assertEqual(main._route("POST", "/data/refresh", {}, {})[0], 403)
        with patch.object(main, "_user_from_request", return_value={"sub": "fixture", "role": "ADMIN"}):
            self.assertEqual(main._route("POST", "/data/refresh", {"sources": ["unknown"]}, {})[0], 400)

    def test_worker_status_differentiates_one_shot_stale_and_active_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            status_path = data / "processed/refresh_worker_status.json"
            status_path.parent.mkdir()
            with patch.object(main, "settings", dataclasses.replace(main.settings, data_dir=data)):
                for once, age, active in ((True, 0, False), (False, 0, True), (False, 3600, False)):
                    status_path.write_text(json.dumps({"status": "ready", "once": once, "interval_seconds": 60, "last_run": (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()}))
                    self.assertEqual(main._refresh_worker_status()["active"], active)

    def test_timeline_bounds_include_entire_end_day_and_reject_reversed_dates(self):
        with patch.object(main, "_user_from_request", return_value={"sub": "fixture"}):
            status, body = main._route("GET", "/timeline?start=2024-02-26&end=2024-02-26", {}, {})
            self.assertEqual(status, 200)
            self.assertTrue(body["events"])
            self.assertTrue(all(row["date"].startswith("2024-02-26") for row in body["events"]))
            self.assertEqual(main._route("GET", "/timeline?start=2025-01-02&end=2025-01-01", {}, {})[0], 400)
            self.assertEqual(main._route("GET", "/timeline?start=not-a-date", {}, {})[0], 400)
