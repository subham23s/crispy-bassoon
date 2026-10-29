"""Real data-stage execution in isolated directories; network responses are fixtures."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/data"))
common = importlib.import_module("common")
nvd = importlib.import_module("ingest_nvd")
bootstrap = importlib.import_module("bootstrap_data")


class DataJobTests(unittest.TestCase):
    def test_nvd_truncated_update_resumes_without_skipping_unfetched_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            with patch.object(common, "DATA_DIR", data), patch.object(common, "MANIFEST_PATH", data / "data_manifest.json"), patch.object(nvd, "DATA_DIR", data):
                common.ensure_data_dirs()
                common.write_json(data / "raw/nvd/state.json", {"last_modified_start": "2026-01-01T00:00:00Z"})
                first = {"totalResults": 2, "vulnerabilities": [{"cve": {"id": "CVE-TEST-0001", "descriptions": [{"lang": "en", "value": "Test fixture, not intelligence."}]}}]}
                second = {"totalResults": 2, "vulnerabilities": [{"cve": {"id": "CVE-TEST-0002", "descriptions": [{"lang": "en", "value": "Second test fixture."}]}}]}
                with patch.object(nvd, "fetch_bytes", side_effect=[json.dumps(first).encode(), json.dumps(second).encode()]) as fetch:
                    partial = nvd.ingest(update=True, limit=1, max_pages=1)
                    state = common.load_json(data / "raw/nvd/state.json")
                    self.assertEqual(partial["status"], "partial")
                    self.assertEqual(state["last_modified_start"], "2026-01-01T00:00:00Z")
                    completed = nvd.ingest(update=True, limit=1, max_pages=1)
                self.assertEqual(completed["status"], "processed")
                queries = [parse_qs(urlparse(call.args[0]).query) for call in fetch.call_args_list]
                self.assertEqual(queries[0]["lastModEndDate"], queries[1]["lastModEndDate"])
                self.assertEqual(queries[1]["startIndex"], ["1"])
                state = common.load_json(data / "raw/nvd/state.json")
                self.assertNotIn("pending_update", state)
                self.assertEqual(state["last_modified_start"], queries[1]["lastModEndDate"][0])
                self.assertEqual(len(list(common.read_jsonl(data / "normalized/nvd.jsonl"))), 2)

    def test_cached_worker_processes_only_configured_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            raw = data / "raw/cisa/known_exploited_vulnerabilities.json"
            raw.parent.mkdir(parents=True)
            raw.write_text(json.dumps({"catalogVersion": "test-fixture", "vulnerabilities": [{"cveID": "CVE-TEST-0001", "vulnerabilityName": "Controlled fixture", "shortDescription": "Test data only, never authoritative intelligence."}]}))
            env = {**os.environ, "DATA_DIR": str(data), "PYTHONPATH": str(ROOT / "backend")}
            result = subprocess.run([sys.executable, str(ROOT / "scripts/refresh_worker.py"), "--once", "--cached", "--sources", "cisa_kev"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            state = json.loads(result.stdout)
            self.assertTrue(state["once"])
            self.assertFalse(state["fresh_download_requested"])
            self.assertTrue((data / "processed/vector_index.sqlite").exists())
            self.assertEqual(len(list(common.read_jsonl(data / "normalized/cyber_entities.jsonl"))), 1)
            self.assertEqual(json.loads((data / "graph/cyber_graph.json").read_text())["nodes"][0]["source_id"], "CVE-TEST-0001")
            process = subprocess.Popen([sys.executable, str(ROOT / "scripts/refresh_worker.py"), "--interval", "60", "--cached", "--sources", "cisa_kev"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try:
                for _ in range(150):
                    state = json.loads((data / "processed/refresh_worker_status.json").read_text())
                    if not state["once"]:
                        break
                    if process.poll() is not None:
                        self.fail(process.stderr.read())
                    time.sleep(0.2)
                else:
                    self.fail("Scheduled worker did not finish its initial cycle")
                self.assertEqual(state["status"], "ready")
                process.terminate()
                self.assertIn(process.wait(timeout=10), (0, 1, 15))
                state = json.loads((data / "processed/refresh_worker_status.json").read_text())
                if os.name != "nt":
                    self.assertEqual(state["status"], "stopped")
                else:
                    self.assertIn(state["status"], ("ready", "stopped"))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()

    def test_bootstrap_preserves_errors_returned_with_success_exit_code(self):
        result = subprocess.CompletedProcess([], 0, '{"status":"error","error":"offline"}', "")
        with patch.object(bootstrap.subprocess, "run", return_value=result):
            self.assertEqual(bootstrap._run("ingest_cisa_kev.py")["status"], "error")
