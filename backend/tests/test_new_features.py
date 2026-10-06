import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

from app import main
from app.main import app
from app.services.document_jobs import DocumentJobManager
from app.services.graph import EvidenceGraph
from app.verification.nli_verifier import build_verifier


class NewFeatureTests(unittest.TestCase):
    @unittest.skipUnless(TestClient is not None, "FastAPI test dependency is not installed")
    def test_api_stream_and_persistent_workspace_contracts(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous_runtime, previous_url = main.runtime, main.settings.database_url
        def restore():
            main.runtime.close()
            main.runtime = previous_runtime
            object.__setattr__(main.settings, "database_url", previous_url)
        self.addCleanup(restore)
        object.__setattr__(main.settings, "database_url", f"sqlite:///{Path(temporary.name) / 'feature.db'}")
        main.runtime = main.Runtime()
        client = TestClient(app)
        email = f"new-feature-{uuid.uuid4().hex[:10]}@example.test"
        auth = client.post("/auth/register", json={"email": email, "password": "long-enough-password"})
        self.assertEqual(auth.status_code, 201)
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
        stream = client.post("/chat/stream", headers=headers, json={"query": "What does NIST CSF 2.0 provide?"})
        self.assertEqual(stream.status_code, 200)
        self.assertIn("text/event-stream", stream.headers.get("content-type", ""))
        self.assertIn("event: complete", stream.text)
        workspace = client.post("/research/workspaces", headers=headers, json={"name": "Regression workspace"})
        self.assertEqual(workspace.status_code, 201)
        workspace_id = workspace.json()["workspace"]["id"]
        item = client.post(f"/research/workspaces/{workspace_id}/items", headers=headers, json={"title": "Question"})
        note = client.post(f"/research/workspaces/{workspace_id}/notes", headers=headers, json={"body": "Evidence note"})
        self.assertEqual(item.status_code, 201)
        self.assertEqual(note.status_code, 201)
        listed = client.get(f"/research/workspaces/{workspace_id}/notes", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["notes"][0]["body"], "Evidence note")

    def test_explicit_nli_engine_is_labeled(self):
        result = build_verifier(provider="heuristic").verify("The control is required.", "The control is required.")
        self.assertEqual(result.model, "heuristic-overlap-fallback")
        self.assertTrue(result.used_fallback)

    def test_document_job_lifecycle(self):
        class Document:
            document_id = "doc-1"

        def worker(filename, payload, **kwargs):
            time.sleep(0.01)
            return Document()

        manager = DocumentJobManager(worker)
        self.addCleanup(manager.close)
        job = manager.submit(filename="evidence.txt", payload=b"evidence", owner_id="user-1")
        for _ in range(50):
            current = manager.get(job["job_id"], "user-1")
            if current and current["status"] == "COMPLETED":
                break
            time.sleep(0.01)
        self.assertEqual(manager.get(job["job_id"], "user-1")["status"], "COMPLETED")
        self.assertIsNone(manager.get(job["job_id"], "other-user"))

    def test_graph_reads_stored_artifact_when_available(self):
        graph = EvidenceGraph(Path("data"))
        result = graph.search("T1059")
        # Empty-data environments are valid, but a real bootstrap must expose
        # the stored entity rather than a hard-coded relationship.
        if (Path("data/graph/cyber_graph.json")).exists():
            self.assertTrue(result["nodes"])
            self.assertIn("provenance", result)

    def test_calibration_schema_has_no_generated_labels(self):
        schema = Path("data/ml/verification/cers_label_schema.json")
        self.assertTrue(schema.exists())
        payload = json.loads(schema.read_text(encoding="utf-8"))
        self.assertEqual(payload["allowed_human_labels"], ["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNKNOWN"])


if __name__ == "__main__":
    unittest.main()
