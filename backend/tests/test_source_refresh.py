import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import source_refresh as refresh


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.settings = patch.object(refresh, "settings", dataclasses.replace(refresh.settings, data_dir=self.directory))
        self.settings.start()
        self.addCleanup(self.settings.stop)

    @staticmethod
    def result(value, returncode=0):
        return subprocess.CompletedProcess([], returncode, json.dumps(value), "")

    def test_failed_source_cannot_be_successful_due_to_zero_exit_status(self):
        with patch.object(refresh.subprocess, "run", return_value=self.result({"status": "error", "error": "offline"})) as run:
            report = refresh.run_refresh(["cisa_kev"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(json.loads((self.directory / "processed/source_update_status.json").read_text())["status"], "failed")

    def test_malformed_result_and_processing_failure_are_recorded(self):
        with patch.object(refresh.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "not JSON", "")):
            self.assertEqual(refresh.run_refresh(["nvd"])["status"], "failed")
        with patch.object(refresh.subprocess, "run", side_effect=[self.result({"status": "processed"}), self.result({}, 1)]):
            report = refresh.run_refresh(["nvd"])
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["last_successful_update"], [])

    def test_partial_page_failures_are_visible_and_lock_recovers(self):
        with refresh.refresh_lock():
            with self.assertRaises(refresh.RefreshBusy):
                refresh.run_refresh(["nist"])
        source = self.result({"status": "processed", "failures": [{"url": "https://example.test", "error": "offline"}]})
        with patch.object(refresh.subprocess, "run", side_effect=[source] + [self.result({"records": 1})] * 6) as run:
            report = refresh.run_refresh(["nist"], force=True)
        self.assertEqual(report["status"], "partial")
        self.assertTrue(report["failures"])
        self.assertIn("--force", run.call_args_list[0].args[0])

    def test_progress_logs_before_pretty_json_and_invalid_selection(self):
        self.assertEqual(refresh._last_json('progress\n{\n  "status": "processed"\n}'), {"status": "processed"})
        for selection in ([], ["not-a-source"]):
            with self.assertRaises(ValueError):
                refresh.run_refresh(selection)

    def test_nvd_live_update_has_no_unsupported_force_flag(self):
        with patch.object(refresh.subprocess, "run", return_value=self.result({"status": "error"})) as run:
            refresh.run_refresh(["nvd"], force=True)
        self.assertIn("--update", run.call_args.args[0])
        self.assertNotIn("--force", run.call_args.args[0])

    def test_processing_semantic_errors_are_not_hidden_by_success_exit_code(self):
        with patch.object(refresh.subprocess, "run", side_effect=[self.result({"status": "processed"}), self.result({"status": "error"})]):
            self.assertEqual(refresh.run_refresh(["cisa_kev"])["status"], "failed")
