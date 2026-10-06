"""PostgreSQL/pgvector repository.

The module has no hard dependency at import time.  A configured PostgreSQL URL
is selected only when SQLAlchemy and a PostgreSQL DBAPI are installed and the
server passes a real connectivity check.  Failed initialization is surfaced to
the infrastructure manager, which then selects SQLite rather than pretending
that an external database is available.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any

from .health import ServiceHealth, unavailable
from .models import as_record


class AdapterUnavailable(RuntimeError):
    """Raised when an optional production adapter cannot be initialized."""


POSTGRES_MIGRATIONS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER', created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS answers (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), answer_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_answers_owner_created ON answers(owner_id, created_at DESC)",
    "CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, settings_json JSONB NOT NULL DEFAULT '{}'::jsonb)",
    "CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, source TEXT NOT NULL, checksum TEXT NOT NULL, status TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS document_metadata (document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE, page_count INTEGER, language TEXT, publication_date TEXT, update_date TEXT, version TEXT, authority_score DOUBLE PRECISION, tags_json JSONB NOT NULL DEFAULT '[]'::jsonb)",
    "CREATE TABLE IF NOT EXISTS document_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, page_number INTEGER, section TEXT, text TEXT NOT NULL, UNIQUE(document_id, ordinal))",
    "CREATE TABLE IF NOT EXISTS embeddings (chunk_id TEXT PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE, model_name TEXT NOT NULL, vector_json JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS vector_embeddings (chunk_id TEXT PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE, model_name TEXT NOT NULL, embedding vector(1536) NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS claims (id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE, claim TEXT NOT NULL, status TEXT NOT NULL, support_score DOUBLE PRECISION NOT NULL, citations_json JSONB NOT NULL DEFAULT '[]'::jsonb)",
    "CREATE TABLE IF NOT EXISTS citations (id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE, chunk_id TEXT NOT NULL REFERENCES document_chunks(id), locator_json JSONB NOT NULL DEFAULT '{}'::jsonb)",
    "CREATE TABLE IF NOT EXISTS verification_results (id TEXT PRIMARY KEY, claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE, status TEXT NOT NULL, support_score DOUBLE PRECISION NOT NULL, explanation TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS research_papers (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), document_id TEXT NOT NULL REFERENCES documents(id), record_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS research_gaps (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, observation TEXT NOT NULL, evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cyber_entities (id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, canonical_name TEXT NOT NULL, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, UNIQUE(entity_type, canonical_name))",
    "CREATE TABLE IF NOT EXISTS cyber_relationships (id TEXT PRIMARY KEY, source_entity_id TEXT NOT NULL REFERENCES cyber_entities(id), relationship_type TEXT NOT NULL, target_entity_id TEXT NOT NULL REFERENCES cyber_entities(id), evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb, UNIQUE(source_entity_id, relationship_type, target_entity_id))",
    "CREATE TABLE IF NOT EXISTS threats (id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id) ON DELETE SET NULL, record_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS vulnerabilities (id TEXT PRIMARY KEY, cve_id TEXT NOT NULL UNIQUE, record_json JSONB NOT NULL DEFAULT '{}'::jsonb, retrieved_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS iocs (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), ioc_type TEXT NOT NULL, value_hash TEXT NOT NULL, record_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL, UNIQUE(owner_id, ioc_type, value_hash))",
    "CREATE TABLE IF NOT EXISTS research_items (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, owner_id TEXT NOT NULL REFERENCES users(id), item_type TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', source_document_id TEXT REFERENCES documents(id) ON DELETE SET NULL, data_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, owner_id TEXT NOT NULL REFERENCES users(id), research_item_id TEXT REFERENCES research_items(id) ON DELETE SET NULL, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS saved_evidence (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, owner_id TEXT NOT NULL REFERENCES users(id), evidence_id TEXT NOT NULL, snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb, note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL, UNIQUE(workspace_id, evidence_id))",
    "CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL, name TEXT NOT NULL, dataset TEXT, model TEXT, hyperparameters_json JSONB NOT NULL DEFAULT '{}'::jsonb, notes TEXT, status TEXT NOT NULL DEFAULT 'created', created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS experiment_metrics (id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE, metric_name TEXT NOT NULL, metric_value DOUBLE PRECISION NOT NULL, UNIQUE(experiment_id, metric_name))",
    "CREATE TABLE IF NOT EXISTS ingestion_jobs (id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id) ON DELETE SET NULL, workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', input_ref TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ)",
    "CREATE TABLE IF NOT EXISTS audit_logs (id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id) ON DELETE SET NULL, action TEXT NOT NULL, request_id TEXT, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS admin_records (id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id) ON DELETE SET NULL, record_type TEXT NOT NULL, subject_id TEXT, data_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE TABLE IF NOT EXISTS refresh_tokens (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at BIGINT NOT NULL, revoked_at BIGINT, created_at TIMESTAMPTZ NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_documents_owner_created ON documents(owner_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cyber_entities_name ON cyber_entities(canonical_name)",
    "CREATE INDEX IF NOT EXISTS idx_cyber_relationships_source ON cyber_relationships(source_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_iocs_owner_type ON iocs(owner_id, ioc_type)",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_document_ordinal ON document_chunks(document_id, ordinal)",
    "CREATE INDEX IF NOT EXISTS idx_research_items_workspace_updated ON research_items(workspace_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_notes_workspace_updated ON notes(workspace_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status_created ON ingestion_jobs(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created ON audit_logs(actor_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_vector_embeddings_hnsw ON vector_embeddings USING hnsw (embedding vector_cosine_ops)",
    "INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT (version) DO NOTHING",
)


class PostgresRepository:
    backend_name = "postgresql-pgvector"

    def __init__(self, url: str, *, pool_size: int = 5, max_overflow: int = 10, timeout: float = 2.0, initialize: bool = True) -> None:
        # SQLAlchemy's bare postgresql:// URL selects psycopg2, whereas the
        # supported requirements install psycopg 3. Preserve explicit drivers.
        self.url = url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                self.url = "postgresql+psycopg://" + url[len(prefix):]
                break
        self.health = unavailable("postgresql", True, "not initialized")
        try:
            from sqlalchemy import create_engine, text  # type: ignore
        except ImportError as exc:
            raise AdapterUnavailable("SQLAlchemy is not installed") from exc
        self._text = text
        try:
            self.engine = create_engine(self.url, pool_pre_ping=True, pool_size=pool_size, max_overflow=max_overflow, pool_timeout=timeout, connect_args={"connect_timeout": max(1, int(timeout))})
            started = time.monotonic()
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            self.health = ServiceHealth("postgresql", True, True, "connected", latency_ms=round((time.monotonic() - started) * 1000, 2))
            if initialize:
                self.initialize()
        except Exception as exc:
            self.close()
            raise AdapterUnavailable(f"PostgreSQL initialization failed: {type(exc).__name__}: {exc}") from exc

    def initialize(self) -> None:
        """Apply idempotent schema, constraints, and pgvector indexes."""
        with self.engine.begin() as connection:
            for migration in POSTGRES_MIGRATIONS:
                connection.execute(self._text(migration))

    def health_check(self) -> ServiceHealth:
        try:
            started = time.monotonic()
            with self.engine.connect() as connection:
                connection.execute(self._text("SELECT 1"))
            self.health = ServiceHealth("postgresql", True, True, "ready", latency_ms=round((time.monotonic() - started) * 1000, 2))
        except Exception as exc:
            self.health = unavailable("postgresql", True, f"PostgreSQL health check failed: {type(exc).__name__}: {exc}")
        return self.health

    def _fetchone(self, query: str, params: dict[str, Any]) -> Any:
        with self.engine.connect() as connection:
            row = connection.execute(self._text(query), params).mappings().first()
            return {key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in row.items()} if row is not None else None

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [{key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in row.items()} for row in connection.execute(self._text(query), params).mappings().all()]

    def create_user(self, user_id: str, email: str, password_hash: str, role: str, created_at: str) -> dict[str, Any]:
        values = {"id": user_id, "email": email.lower(), "password_hash": password_hash, "role": role, "created_at": created_at}
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO users(id,email,password_hash,role,created_at) VALUES(:id,:email,:password_hash,:role,:created_at)"), values)
        return {"id": user_id, "email": email.lower(), "role": role, "created_at": created_at}

    def get_user_by_email(self, email: str) -> Any:
        return self._fetchone("SELECT * FROM users WHERE email = :email", {"email": email.lower()})

    def get_user(self, user_id: str) -> Any:
        rows = self._fetchall("SELECT id,email,role,created_at FROM users WHERE id = :id", {"id": user_id})
        return rows[0] if rows else None

    def list_users(self) -> list[dict[str, Any]]:
        return self._fetchall("SELECT id,email,role,created_at FROM users ORDER BY created_at DESC", {})

    def list_documents(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT * FROM documents WHERE owner_id = :owner_id ORDER BY created_at DESC", {"owner_id": owner_id})
        for row in rows:
            row["metadata"] = row.pop("metadata_json") or {}
        return rows

    def list_all_documents(self) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT * FROM documents ORDER BY created_at DESC", {})
        for row in rows:
            row["metadata"] = row.pop("metadata_json") or {}
        return rows

    def get_document(self, document_id: str, owner_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM documents WHERE id = :id AND owner_id = :owner_id", {"id": document_id, "owner_id": owner_id})
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = result.pop("metadata_json") or {}
        return result

    def save_document(self, document_id: str, owner_id: str, title: str, source: str, checksum: str, status: str, metadata: dict[str, Any], created_at: str) -> None:
        params = {"id": document_id, "owner_id": owner_id, "title": title, "source": source, "checksum": checksum, "status": status, "metadata": json.dumps(metadata), "created_at": created_at}
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO documents(id,owner_id,title,source,checksum,status,metadata_json,created_at) VALUES(:id,:owner_id,:title,:source,:checksum,:status,CAST(:metadata AS jsonb),:created_at) ON CONFLICT(id) DO UPDATE SET title=EXCLUDED.title,source=EXCLUDED.source,checksum=EXCLUDED.checksum,status=EXCLUDED.status,metadata_json=EXCLUDED.metadata_json WHERE documents.owner_id=EXCLUDED.owner_id"), params)

    def save_chunks(self, document_id: str, owner_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.engine.begin() as connection:
            document = connection.execute(self._text("SELECT id FROM documents WHERE id=:id AND owner_id=:owner_id FOR UPDATE"), {"id": document_id, "owner_id": owner_id}).first()
            if document is None:
                raise ValueError("Document not found")
            for chunk in chunks:
                result = connection.execute(self._text("INSERT INTO document_chunks(id,document_id,ordinal,page_number,section,text) VALUES(:id,:document_id,:ordinal,:page_number,:section,:text) ON CONFLICT(id) DO UPDATE SET ordinal=EXCLUDED.ordinal,page_number=EXCLUDED.page_number,section=EXCLUDED.section,text=EXCLUDED.text WHERE document_chunks.document_id=EXCLUDED.document_id"), {"id": chunk["chunk_id"], "document_id": document_id, "ordinal": chunk["ordinal"], "page_number": chunk.get("page_number"), "section": chunk.get("section", ""), "text": chunk["text"]})
                if result.rowcount != 1:
                    raise ValueError("Chunk belongs to another document")

    def list_chunks(self, document_id: str, owner_id: str) -> list[dict[str, Any]]:
        return self._fetchall("SELECT c.* FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE d.id=:id AND d.owner_id=:owner_id AND d.status='indexed' ORDER BY c.ordinal", {"id": document_id, "owner_id": owner_id})

    def save_answer(self, owner_id: str, answer: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO answers(id,owner_id,answer_json,created_at) VALUES(:id,:owner_id,CAST(:answer AS jsonb),:created_at)"), {"id": answer["answer_id"], "owner_id": owner_id, "answer": json.dumps(answer), "created_at": answer["created_at"]})

    def get_answer(self, answer_id: str, owner_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT answer_json FROM answers WHERE id=:id AND owner_id=:owner_id", {"id": answer_id, "owner_id": owner_id})
        return row["answer_json"] if row else None

    def list_answers(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return [row["answer_json"] for row in self._fetchall("SELECT answer_json FROM answers WHERE owner_id=:owner_id ORDER BY created_at DESC LIMIT :limit", {"owner_id": owner_id, "limit": min(max(limit, 1), 200)})]

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(self._text("DELETE FROM documents WHERE id = :id AND owner_id = :owner_id"), {"id": document_id, "owner_id": owner_id})
        return result.rowcount == 1

    def save_refresh_token(self, token_hash: str, user_id: str, expires_at: int, created_at: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO refresh_tokens(token_hash,user_id,expires_at,created_at) VALUES(:token_hash,:user_id,:expires_at,:created_at)"), locals())

    def get_refresh_token(self, token_hash: str) -> Any:
        return self._fetchone("SELECT * FROM refresh_tokens WHERE token_hash = :token_hash AND revoked_at IS NULL", {"token_hash": token_hash})

    def revoke_refresh_token(self, token_hash: str, revoked_at: int) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(self._text("UPDATE refresh_tokens SET revoked_at = :revoked_at WHERE token_hash = :token_hash AND revoked_at IS NULL"), {"token_hash": token_hash, "revoked_at": revoked_at})
        return result.rowcount == 1

    def save_audit(self, audit_id: str, actor_id: str | None, action: str, request_id: str, metadata: dict[str, Any], created_at: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO audit_logs(id,actor_id,action,request_id,metadata_json,created_at) VALUES(:id,:actor_id,:action,:request_id,CAST(:metadata AS jsonb),:created_at)"), {"id": audit_id, "actor_id": actor_id, "action": action, "request_id": request_id, "metadata": json.dumps(metadata), "created_at": created_at})

    def _save_record(self, table: str, columns: tuple[str, ...], params: dict[str, Any], json_columns: tuple[str, ...] = ()) -> dict[str, Any]:
        safe_columns = ",".join(columns)
        placeholders = ",".join(f":{column}" for column in columns)
        assignments = ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column != "id")
        query = f"INSERT INTO {table}({safe_columns}) VALUES({placeholders}) ON CONFLICT(id) DO UPDATE SET {assignments}"
        if "owner_id" in columns:
            query += f" WHERE {table}.owner_id=EXCLUDED.owner_id"
        encoded = dict(params)
        for key in json_columns:
            encoded[key] = json.dumps(encoded.get(key, {}))
            query = query.replace(f":{key}", f"CAST(:{key} AS jsonb)")
        with self.engine.begin() as connection:
            connection.execute(self._text(query), encoded)
        return params

    def save_workspace(self, workspace: Any) -> dict[str, Any]:
        record = as_record(workspace)
        return self._save_record("workspaces", ("id", "owner_id", "name", "created_at", "settings_json"), {"id": record["id"], "owner_id": record["owner_id"], "name": record["name"], "created_at": record["created_at"], "settings_json": record.get("settings", {})}, ("settings_json",))

    def list_workspaces(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT id,owner_id,name,created_at,settings_json FROM workspaces WHERE owner_id=:owner_id ORDER BY created_at DESC", {"owner_id": owner_id})
        for row in rows: row["settings"] = row.pop("settings_json") or {}
        return rows

    def save_research_item(self, item: Any) -> dict[str, Any]:
        r = as_record(item)
        return self._save_record("research_items", ("id", "workspace_id", "owner_id", "item_type", "title", "status", "source_document_id", "data_json", "created_at", "updated_at"), {"id": r["id"], "workspace_id": r["workspace_id"], "owner_id": r["owner_id"], "item_type": r["item_type"], "title": r["title"], "status": r.get("status", "active"), "source_document_id": r.get("source_document_id"), "data_json": r.get("data", {}), "created_at": r["created_at"], "updated_at": r.get("updated_at") or r["created_at"]}, ("data_json",))

    def list_research_items(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT * FROM research_items WHERE workspace_id=:workspace_id AND owner_id=:owner_id ORDER BY updated_at DESC", {"workspace_id": workspace_id, "owner_id": owner_id})
        for row in rows: row["data"] = row.pop("data_json") or {}
        return rows

    def save_note(self, note: Any) -> dict[str, Any]:
        r = as_record(note)
        return self._save_record("notes", ("id", "workspace_id", "owner_id", "research_item_id", "title", "body", "created_at", "updated_at"), {"id": r["id"], "workspace_id": r["workspace_id"], "owner_id": r["owner_id"], "research_item_id": r.get("research_item_id"), "title": r.get("title", ""), "body": r["body"], "created_at": r["created_at"], "updated_at": r.get("updated_at") or r["created_at"]})

    def list_notes(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        return self._fetchall("SELECT * FROM notes WHERE workspace_id=:workspace_id AND owner_id=:owner_id ORDER BY updated_at DESC", {"workspace_id": workspace_id, "owner_id": owner_id})

    def save_evidence(self, evidence: Any) -> dict[str, Any]:
        r = as_record(evidence)
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO saved_evidence(id,workspace_id,owner_id,evidence_id,snapshot_json,note,created_at) VALUES(:id,:workspace_id,:owner_id,:evidence_id,CAST(:snapshot AS jsonb),:note,:created_at) ON CONFLICT(workspace_id,evidence_id) DO UPDATE SET snapshot_json=EXCLUDED.snapshot_json,note=EXCLUDED.note WHERE saved_evidence.owner_id=EXCLUDED.owner_id"), {**r, "snapshot": json.dumps(r.get("snapshot", {}))})
        return next(item for item in self.list_saved_evidence(r["workspace_id"], r["owner_id"]) if item["evidence_id"] == r["evidence_id"])

    def list_saved_evidence(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT * FROM saved_evidence WHERE workspace_id=:workspace_id AND owner_id=:owner_id ORDER BY created_at DESC", {"workspace_id": workspace_id, "owner_id": owner_id})
        for row in rows: row["snapshot"] = row.pop("snapshot_json") or {}
        return rows

    def save_experiment(self, experiment: Any) -> dict[str, Any]:
        r = as_record(experiment)
        return self._save_record("experiments", ("id", "owner_id", "workspace_id", "name", "dataset", "model", "hyperparameters_json", "notes", "status", "created_at", "updated_at"), {"id": r["id"], "owner_id": r["owner_id"], "workspace_id": r.get("workspace_id"), "name": r["name"], "dataset": r.get("dataset", ""), "model": r.get("model", ""), "hyperparameters_json": r.get("hyperparameters", {}), "notes": r.get("notes", ""), "status": r.get("status", "created"), "created_at": r["created_at"], "updated_at": r.get("updated_at") or r["created_at"]}, ("hyperparameters_json",))

    def list_experiments(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall("SELECT * FROM experiments WHERE owner_id=:owner_id ORDER BY created_at DESC", {"owner_id": owner_id})
        for row in rows: row["hyperparameters"] = row.pop("hyperparameters_json") or {}
        return rows

    def save_experiment_metric(self, metric_id: str, experiment_id: str, metric_name: str, metric_value: float) -> None:
        with self.engine.begin() as connection:
            connection.execute(self._text("INSERT INTO experiment_metrics(id,experiment_id,metric_name,metric_value) VALUES(:id,:experiment_id,:metric_name,:metric_value) ON CONFLICT(experiment_id,metric_name) DO UPDATE SET metric_value=EXCLUDED.metric_value"), {"id": metric_id, "experiment_id": experiment_id, "metric_name": metric_name, "metric_value": metric_value})

    def list_experiment_metrics(self, experiment_id: str) -> list[dict[str, Any]]:
        return self._fetchall("SELECT * FROM experiment_metrics WHERE experiment_id=:experiment_id ORDER BY metric_name", {"experiment_id": experiment_id})

    def delete_experiment(self, experiment_id: str, owner_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(self._text("DELETE FROM experiments WHERE id=:id AND owner_id=:owner_id"), {"id": experiment_id, "owner_id": owner_id})
        return result.rowcount == 1

    def save_ingestion_job(self, job: Any) -> dict[str, Any]:
        r = as_record(job)
        return self._save_record("ingestion_jobs", ("id", "owner_id", "workspace_id", "source", "status", "input_ref", "error", "metadata_json", "created_at", "started_at", "finished_at"), {"id": r["id"], "owner_id": r.get("owner_id"), "workspace_id": r.get("workspace_id"), "source": r["source"], "status": r.get("status", "queued"), "input_ref": r.get("input_ref", ""), "error": r.get("error", ""), "metadata_json": r.get("metadata", {}), "created_at": r["created_at"], "started_at": r.get("started_at"), "finished_at": r.get("finished_at")}, ("metadata_json",))

    def list_ingestion_jobs(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM ingestion_jobs"
        params: dict[str, Any] = {}
        if owner_id is not None:
            query += " WHERE owner_id=:owner_id"
            params["owner_id"] = owner_id
        rows = self._fetchall(query + " ORDER BY created_at DESC", params)
        for row in rows:
            row["metadata"] = row.pop("metadata_json") or {}
        return rows

    def get_ingestion_job(self, job_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM ingestion_jobs WHERE id=:id"
        params: dict[str, Any] = {"id": job_id}
        if owner_id is not None:
            query += " AND owner_id=:owner_id"
            params["owner_id"] = owner_id
        row = self._fetchone(query, params)
        if row is None: return None
        result = dict(row); result["metadata"] = result.pop("metadata_json") or {}; return result

    def update_ingestion_job(self, job_id: str, status: str, *, error: str = "", started_at: str | None = None, finished_at: str | None = None) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(self._text("UPDATE ingestion_jobs SET status=:status,error=:error,started_at=COALESCE(:started_at,started_at),finished_at=COALESCE(:finished_at,finished_at) WHERE id=:id"), {"id": job_id, "status": status, "error": error, "started_at": started_at, "finished_at": finished_at})
        return result.rowcount == 1

    def list_audit(self, actor_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_logs"
        params: dict[str, Any] = {}
        if actor_id is not None:
            query += " WHERE actor_id=:actor_id"
            params["actor_id"] = actor_id
        rows = self._fetchall(query + " ORDER BY created_at DESC", params)
        for row in rows: row["metadata"] = row.pop("metadata_json") or {}
        return rows

    def save_admin_record(self, record: Any) -> dict[str, Any]:
        r = as_record(record)
        return self._save_record("admin_records", ("id", "actor_id", "record_type", "subject_id", "data_json", "created_at"), {"id": r["id"], "actor_id": r.get("actor_id"), "record_type": r["record_type"], "subject_id": r.get("subject_id"), "data_json": r.get("data", {}), "created_at": r["created_at"]}, ("data_json",))

    def close(self) -> None:
        engine = getattr(self, "engine", None)
        if engine is not None:
            engine.dispose()
