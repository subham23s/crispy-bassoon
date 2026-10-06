"""Exercise the actual persistence/API lifecycle without external services."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main
from app.services.corpus import DocumentStore


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.previous_runtime = main.runtime
        cls.previous_url = main.settings.database_url
        object.__setattr__(main.settings, "database_url", f"sqlite:///{Path(cls.temporary.name) / 'experiments.db'}")
        with patch.object(main, "DocumentStore", side_effect=lambda **_: DocumentStore()):
            main.runtime = main.Runtime()
        cls.headers = []
        for email in ("experiment-owner@example.test", "experiment-other@example.test"):
            status, session = main._route("POST", "/auth/register", {"email": email, "password": "correct horse battery"}, {})
            assert status == 201
            cls.headers.append({"authorization": f"Bearer {session['access_token']}"})

    @classmethod
    def tearDownClass(cls):
        main.runtime.close()
        main.runtime = cls.previous_runtime
        object.__setattr__(main.settings, "database_url", cls.previous_url)
        cls.temporary.cleanup()

    def request(self, method, path, payload=None, owner=0):
        return main._route(method, path, payload or {}, self.headers[owner])

    def create(self):
        status, body = self.request("POST", "/experiments", {"name": "Recorded run", "hyperparameters": {"seed": 42}})
        self.assertEqual(status, 201, body)
        return body["experiment"]["id"]

    def test_lifecycle_retains_metrics_when_editing_and_survives_repository_reopen(self):
        experiment_id = self.create()
        path = f"/experiments/{experiment_id}"
        for value in (0.25, -0.125):  # Test inputs, not evaluation results.
            status, body = self.request("POST", path + "/metrics", {"name": "test fixture delta", "value": value})
            self.assertEqual(status, 201, body)
        status, body = self.request("PATCH", path, {"status": "completed", "notes": "Unit-test fixture only"})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body["experiment"]["metrics"]), 1)
        self.assertEqual(body["experiment"]["metrics"][0]["metric_value"], -0.125)
        from app.database.sqlite import SQLiteRepository
        reopened = SQLiteRepository(main.runtime.repository.path)
        self.assertEqual(reopened.list_experiment_metrics(experiment_id)[0]["metric_value"], -0.125)
        self.assertEqual(self.request("DELETE", path)[0], 200)
        self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(reopened.list_experiment_metrics(experiment_id), [])

    def test_cross_owner_operations_are_rejected(self):
        path = f"/experiments/{self.create()}"
        for method, suffix, payload in (("GET", "", {}), ("PATCH", "", {"name": "Changed"}), ("DELETE", "", {}), ("POST", "/metrics", {"name": "x", "value": 1})):
            self.assertEqual(self.request(method, path + suffix, payload, owner=1)[0], 404)

    def test_invalid_metrics_and_experiment_metadata_do_not_persist(self):
        path = f"/experiments/{self.create()}/metrics"
        for value in (None, True, "1", float("nan"), float("inf"), []):
            self.assertEqual(self.request("POST", path, {"name": "invalid", "value": value})[0], 400)
        self.assertEqual(self.request("POST", path, {"name": " ", "value": 1})[0], 400)
        for payload in ({"name": "x", "hyperparameters": []}, {"name": "x", "status": "invented"}, {"name": "x", "workspace_id": "missing"}):
            self.assertEqual(self.request("POST", "/experiments", payload)[0], 400)

    def test_workspace_evidence_bookmark_is_idempotent(self):
        status, body = self.request("POST", "/research/workspaces", {"name": "Evidence fixture"})
        self.assertEqual(status, 201)
        path = f"/research/workspaces/{body['workspace']['id']}/evidence"
        payload = {"evidence_id": "seed-nist-csf-2-0:chunk:0", "note": "Original note"}
        status, first = self.request("POST", path, payload)
        self.assertEqual(status, 201)
        payload["note"] = "Updated note"
        status, second = self.request("POST", path, payload)
        self.assertEqual(status, 201)
        self.assertEqual(first["evidence"]["id"], second["evidence"]["id"])
        self.assertEqual(len(self.request("GET", path)[1]["evidence"]), 1)
        self.assertEqual(self.request("GET", path, owner=1)[0], 404)


if __name__ == "__main__":
    unittest.main()
