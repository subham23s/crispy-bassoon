"""Infrastructure tests that never claim an unavailable service is healthy."""
from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.database import (
    AdminRecord,
    Experiment,
    Infrastructure,
    IngestionJob,
    Note,
    ResearchItem,
    SavedEvidence,
    SQLiteRepository,
    Workspace,
)
from app.database.redis_adapter import RedisAdapter


class SQLitePersistenceTests(unittest.TestCase):
    def test_research_workspace_and_operational_records_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteRepository(Path(directory) / "records.db")
            repository.create_user("u1", "owner@example.test", "hash", "USER", "2025-01-01T00:00:00+00:00")
            repository.save_workspace(Workspace("w1", "u1", "Research", "2025-01-01T00:00:00+00:00"))
            repository.save_research_item(ResearchItem("r1", "w1", "u1", "paper", "A paper", created_at="2025-01-01T00:00:00+00:00"))
            repository.save_note(Note("n1", "w1", "u1", "Useful note", research_item_id="r1", created_at="2025-01-01T00:00:00+00:00"))
            repository.save_evidence(SavedEvidence("e1", "w1", "u1", "chunk-1", {"text": "quoted"}, created_at="2025-01-01T00:00:00+00:00"))
            repository.save_experiment(Experiment("x1", "u1", "baseline", workspace_id="w1", created_at="2025-01-01T00:00:00+00:00"))
            repository.save_ingestion_job(IngestionJob("j1", "u1", "w1", "upload", created_at="2025-01-01T00:00:00+00:00"))
            repository.save_admin_record(AdminRecord("a1", "u1", "permission_change", created_at="2025-01-01T00:00:00+00:00"))

            self.assertEqual(repository.list_workspaces("u1")[0]["id"], "w1")
            self.assertEqual(repository.list_research_items("w1", "u1")[0]["data"], {})
            self.assertEqual(repository.list_notes("w1", "u1")[0]["body"], "Useful note")
            self.assertEqual(repository.list_saved_evidence("w1", "u1")[0]["snapshot"]["text"], "quoted")
            self.assertEqual(repository.list_experiments("u1")[0]["name"], "baseline")
            self.assertEqual(repository.get_ingestion_job("j1", "u1")["status"], "queued")


class OptionalInfrastructureTests(unittest.TestCase):
    def test_empty_redis_url_is_disabled_not_healthy(self):
        adapter = RedisAdapter("")
        self.assertFalse(adapter.available)
        self.assertEqual(adapter.health.state, "disabled")
        self.assertIn("not configured", adapter.health.reason)

    def test_unavailable_postgres_falls_back_and_keeps_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            config = dataclasses.replace(settings, database_url="postgresql://invalid:invalid@127.0.0.1:1/nope", data_dir=Path(directory), redis_url="", neo4j_uri="", service_connect_timeout=0.1)
            infrastructure = Infrastructure(config)
            report = infrastructure.health()
            self.assertEqual(report["repository_backend"], "sqlite")
            self.assertFalse(report["services"]["database"]["available"])
            self.assertTrue(report["services"]["database"]["degraded"])
            self.assertIn("PostgreSQL unavailable", report["services"]["database"]["reason"])
            infrastructure.close()

    def test_sqlite_runtime_reports_optional_services_without_fabricating_them(self):
        with tempfile.TemporaryDirectory() as directory:
            config = dataclasses.replace(settings, database_url=f"sqlite:///{Path(directory) / 'runtime.db'}", redis_url="", neo4j_uri="")
            infrastructure = Infrastructure(config)
            report = infrastructure.health()
            self.assertEqual(report["repository_backend"], "sqlite")
            self.assertTrue(report["services"]["database"]["available"])
            self.assertFalse(report["services"]["redis"]["available"])
            self.assertFalse(report["services"]["neo4j"]["available"])
            self.assertEqual(report["services"]["redis"]["state"], "disabled")
            infrastructure.close()

    @unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "TEST_POSTGRES_URL is not configured; no PostgreSQL connection is fabricated")
    def test_configured_postgres_is_real_when_available(self):
        config = dataclasses.replace(settings, database_url=os.environ["TEST_POSTGRES_URL"])
        infrastructure = Infrastructure(config)
        self.assertTrue(infrastructure.health()["services"]["database"]["available"])
        self.assertEqual(infrastructure.health()["repository_backend"], "postgresql-pgvector")
        infrastructure.close()


if __name__ == "__main__":
    unittest.main()
