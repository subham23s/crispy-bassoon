"""Opt-in service contracts; each run isolates and removes its own records."""
from __future__ import annotations

import dataclasses
import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.auth.service import AuthService
from app.config import settings
from app.database import Infrastructure, Workspace, Experiment
from app.database.neo4j_adapter import Neo4jAdapter
from app.database.redis_adapter import RedisAdapter
from app.services.graph import EvidenceGraph


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured")
class LivePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        url = make_url(os.environ["TEST_POSTGRES_URL"].replace("postgres://", "postgresql://", 1))
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        cls.admin = create_engine(url)
        cls.schema = "test_" + uuid.uuid4().hex
        with cls.admin.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.addClassCleanup(cls.cleanup_schema)
        url = url.update_query_dict({"options": f"-csearch_path={cls.schema},public"})
        cls.config = dataclasses.replace(settings, database_url=url.render_as_string(hide_password=False), redis_url="", neo4j_uri="")
        cls.infrastructure = Infrastructure(cls.config)
        cls.addClassCleanup(cls.infrastructure.close)
        cls.repository = cls.infrastructure.repository
        if cls.repository.backend_name != "postgresql-pgvector":
            raise AssertionError(cls.infrastructure.health())

    @classmethod
    def cleanup_schema(cls):
        from sqlalchemy import text
        try:
            with cls.admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        finally:
            cls.admin.dispose()

    def setUp(self):
        self.auth = AuthService(self.repository, "live-test-secret")
        self.email = f"{uuid.uuid4().hex}@example.test"
        self.session = self.auth.register(self.email, "live test password")
        self.owner = self.session["user"]["id"]
        self.created = self.session["user"]["created_at"]

    def test_health_authentication_rotation_and_json_serialization(self):
        health = self.infrastructure.health()
        self.assertTrue(health["services"]["database"]["available"])
        self.assertEqual(health["repository_backend"], "postgresql-pgvector")
        json.dumps(self.auth.login(self.email, "live test password"))
        json.dumps(self.auth.refresh(self.session["refresh_token"]))
        with self.assertRaises(ValueError):
            self.auth.refresh(self.session["refresh_token"])

    def test_upload_chunks_answers_and_owner_isolation(self):
        repo = self.repository
        document = uuid.uuid4().hex
        repo.save_document(document, self.owner, "Owned source", "upload", "checksum", "indexed", {"content": "evidence"}, self.created)
        chunk = {"chunk_id": document + ":0", "ordinal": 0, "text": "Attributed evidence", "page_number": 1}
        repo.save_chunks(document, self.owner, [chunk])
        self.assertEqual(repo.list_chunks(document, self.owner)[0]["text"], chunk["text"])
        self.assertEqual(repo.list_chunks(document, "other-user"), [])
        with self.assertRaises(ValueError):
            repo.save_chunks(document, "other-user", [chunk])
        other = self.auth.register(f"{uuid.uuid4().hex}@example.test", "live test password")["user"]["id"]
        repo.save_document(document, other, "overwrite attempt", "upload", "checksum", "indexed", {}, self.created)
        self.assertIsNone(repo.get_document(document, other))
        self.assertEqual(repo.get_document(document, self.owner)["title"], "Owned source")
        answer = {"answer_id": uuid.uuid4().hex, "created_at": self.created, "query": "NIST CSF?", "evidence": [chunk]}
        repo.save_answer(self.owner, answer)
        self.assertEqual(repo.get_answer(answer["answer_id"], self.owner), answer)
        self.assertIsNone(repo.get_answer(answer["answer_id"], other))
        self.assertEqual(repo.list_answers(self.owner, limit=1), [answer])
        json.dumps(repo.get_document(document, self.owner))
        self.assertTrue(repo.delete_document(document, self.owner))
        self.assertEqual(repo.list_chunks(document, self.owner), [])

    def test_fastapi_query_history_report_and_upload_with_postgres(self):
        from fastapi.testclient import TestClient
        from app import main
        with patch.object(main.runtime, "repository", self.repository), patch.object(main.runtime, "auth", self.auth), patch.object(main.runtime, "infrastructure", self.infrastructure):
            client = TestClient(main.app)
            self.addCleanup(client.close)
            headers = {"Authorization": f"Bearer {self.session['access_token']}"}
            health = client.get("/health/detailed")
            self.assertEqual(health.status_code, 200, health.text)
            self.assertTrue(health.json()["capabilities"]["production_postgres"])
            uploaded = client.post("/documents/upload", headers=headers, json={"filename": "contract.txt", "content": "Defensive evidence for a live database integration fixture."})
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            document = uploaded.json()["document"]["document_id"]
            try:
                response = client.post("/chat/query", headers=headers, json={"query": "What does NIST CSF 2.0 provide?"})
                self.assertEqual(response.status_code, 200, response.text)
                answer = response.json()
                history = client.get(f"/chat/answers/{answer['answer_id']}", headers=headers)
                self.assertEqual(history.status_code, 200, history.text)
                exported = client.post("/reports/export", headers=headers, json={"answer_id": answer["answer_id"], "format": "json"})
                self.assertEqual(exported.status_code, 200, exported.text)
                self.assertTrue(exported.json()["content_base64"])
            finally:
                self.assertEqual(client.delete(f"/documents/{document}", headers=headers).status_code, 200)

    def test_experiment_updates_preserve_metrics_and_vector_extension_executes(self):
        from sqlalchemy import text
        repo = self.repository
        workspace = uuid.uuid4().hex
        repo.save_workspace(Workspace(workspace, self.owner, "Live contract", self.created))
        experiment = Experiment(uuid.uuid4().hex, self.owner, "Before", workspace_id=workspace, created_at=self.created)
        repo.save_experiment(experiment)
        repo.save_experiment_metric(uuid.uuid4().hex, experiment.id, "fixture_metric", 0.2)
        repo.save_experiment(dataclasses.replace(experiment, name="After"))
        repo.save_experiment_metric(uuid.uuid4().hex, experiment.id, "fixture_metric", 0.3)
        self.assertEqual(repo.list_experiment_metrics(experiment.id)[0]["metric_value"], 0.3)
        self.assertEqual(repo.list_experiments(self.owner)[0]["name"], "After")
        self.assertFalse(repo.delete_experiment(experiment.id, "another-user"))
        self.assertTrue(repo.delete_experiment(experiment.id, self.owner))
        self.assertEqual(repo.list_experiment_metrics(experiment.id), [])
        with repo.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector")).scalar_one(), 0)


class LiveOptionalServiceTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv("TEST_REDIS_URL"), "TEST_REDIS_URL is not configured")
    def test_redis_round_trip_and_expiration(self):
        adapter = RedisAdapter(os.environ["TEST_REDIS_URL"], timeout=2)
        self.addCleanup(adapter.close)
        self.assertTrue(adapter.available, adapter.health.reason)
        key = "cybersecra-test:" + uuid.uuid4().hex
        self.assertTrue(adapter.set(key, "fixture-value", ex=1))
        self.assertEqual(adapter.get(key), "fixture-value")
        time.sleep(1.1)
        self.assertIsNone(adapter.get(key))

    @unittest.skipUnless(os.getenv("TEST_NEO4J_URI"), "TEST_NEO4J_URI is not configured")
    def test_neo4j_import_idempotence_and_provenance_traversal(self):
        adapter = Neo4jAdapter(os.environ["TEST_NEO4J_URI"], os.getenv("TEST_NEO4J_USERNAME", "neo4j"), os.environ["TEST_NEO4J_PASSWORD"], timeout=5)
        self.addCleanup(adapter.close)
        self.assertTrue(adapter.available, adapter.health.reason)
        prefix = "cybersecra-test:" + uuid.uuid4().hex
        ids = [prefix + ":a", prefix + ":b"]
        self.addCleanup(adapter.execute, "MATCH (n:CyberEntity) WHERE n.id IN $ids DETACH DELETE n", {"ids": ids})
        nodes = [{"id": id_, "name": id_, "entity_type": "TEST", "source": "integration fixture"} for id_ in ids]
        edges = [{"source_entity_id": ids[0], "target_entity_id": ids[1], "relationship_type": "fixture_relation", "resolved": True}]
        for _ in range(2):
            result = adapter.import_graph(nodes, edges)
            self.assertEqual(result["edges_upserted"], 1)
        result = EvidenceGraph(Path("."), adapter).search(ids[0], depth=1)
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(len(result["edges"]), 1)
        self.assertIn("Neo4j", result["provenance"])
