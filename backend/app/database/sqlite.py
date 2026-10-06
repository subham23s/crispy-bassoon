"""Small SQLite persistence layer for local development and tests.

The schema mirrors the production entities and can be replaced by PostgreSQL
repositories without changing service interfaces.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import as_record


SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answer_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_answers_owner_created ON answers(owner_id, created_at DESC);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'USER',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS document_metadata (
    document_id TEXT PRIMARY KEY,
    page_count INTEGER,
    language TEXT,
    publication_date TEXT,
    update_date TEXT,
    version TEXT,
    authority_score REAL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    page_number INTEGER,
    section TEXT,
    text TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS citations (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    locator_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(message_id) REFERENCES messages(id),
    FOREIGN KEY(chunk_id) REFERENCES document_chunks(id)
);
CREATE TABLE IF NOT EXISTS verification_results (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL,
    support_score REAL NOT NULL,
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(claim_id) REFERENCES claims(id)
);
CREATE TABLE IF NOT EXISTS research_papers (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id),
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS research_gaps (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    observation TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    workspace_id TEXT,
    name TEXT NOT NULL,
    dataset TEXT,
    model TEXT,
    hyperparameters_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS experiment_metrics (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    FOREIGN KEY(experiment_id) REFERENCES experiments(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS cyber_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS cyber_relationships (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(source_entity_id) REFERENCES cyber_entities(id),
    FOREIGN KEY(target_entity_id) REFERENCES cyber_entities(id)
);
CREATE TABLE IF NOT EXISTS threats (
    id TEXT PRIMARY KEY,
    owner_id TEXT,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vulnerabilities (
    id TEXT PRIMARY KEY,
    cve_id TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS iocs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    ioc_type TEXT NOT NULL,
    value_hash TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    status TEXT NOT NULL,
    support_score REAL NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(message_id) REFERENCES messages(id)
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    actor_id TEXT,
    action TEXT NOT NULL,
    request_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source_document_id TEXT,
    data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(owner_id) REFERENCES users(id),
    FOREIGN KEY(source_document_id) REFERENCES documents(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    research_item_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(owner_id) REFERENCES users(id),
    FOREIGN KEY(research_item_id) REFERENCES research_items(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS saved_evidence (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, evidence_id),
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(owner_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id TEXT PRIMARY KEY,
    owner_id TEXT,
    workspace_id TEXT,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    input_ref TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS admin_records (
    id TEXT PRIMARY KEY,
    actor_id TEXT,
    record_type TEXT NOT NULL,
    subject_id TEXT,
    data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(actor_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);
CREATE INDEX IF NOT EXISTS idx_research_items_workspace ON research_items(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_workspace ON notes(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status ON ingestion_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created ON audit_logs(actor_id, created_at);
INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, CURRENT_TIMESTAMP);
"""


class SQLiteRepository:
    backend_name = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate_columns(connection)

    @staticmethod
    def _migrate_columns(connection: sqlite3.Connection) -> None:
        """Add columns introduced after the original local schema."""
        migrations = {
            "workspaces": {"settings_json": "TEXT NOT NULL DEFAULT '{}'"},
            "experiments": {
                "workspace_id": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'created'",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        }
        for table, columns in migrations.items():
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_user(self, user_id: str, email: str, password_hash: str, role: str, created_at: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("INSERT INTO users(id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)", (user_id, email.lower(), password_hash, role, created_at))
        return {"id": user_id, "email": email.lower(), "role": role, "created_at": created_at}

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()

    def get_user(self, user_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT id,email,role,created_at FROM users WHERE id = ?", (user_id,)).fetchone()

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id,email,role,created_at FROM users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def list_documents(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM documents WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def list_all_documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def get_document(self, document_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ? AND owner_id = ?", (document_id, owner_id)).fetchone()
        if row is None:
            return None
        return {**dict(row), "metadata": json.loads(row["metadata_json"])}

    def save_document(self, document_id: str, owner_id: str, title: str, source: str, checksum: str, status: str, metadata: dict[str, Any], created_at: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO documents(id,owner_id,title,source,checksum,status,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,source=excluded.source,checksum=excluded.checksum,status=excluded.status,metadata_json=excluded.metadata_json WHERE documents.owner_id=excluded.owner_id", (document_id, owner_id, title, source, checksum, status, json.dumps(metadata), created_at))

    def save_chunks(self, document_id: str, owner_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as connection:
            if not connection.execute("SELECT id FROM documents WHERE id=? AND owner_id=?", (document_id, owner_id)).fetchone():
                raise ValueError("Document not found")
            for chunk in chunks:
                connection.execute("INSERT INTO document_chunks(id,document_id,ordinal,page_number,section,text) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ordinal=excluded.ordinal,page_number=excluded.page_number,section=excluded.section,text=excluded.text", (chunk["chunk_id"], document_id, chunk["ordinal"], chunk.get("page_number"), chunk.get("section", ""), chunk["text"]))

    def list_chunks(self, document_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT c.* FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE d.id=? AND d.owner_id=? AND d.status='indexed' ORDER BY c.ordinal", (document_id, owner_id)).fetchall()
        return [dict(row) for row in rows]

    def save_answer(self, owner_id: str, answer: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO answers(id,owner_id,answer_json,created_at) VALUES(?,?,?,?)", (answer["answer_id"], owner_id, json.dumps(answer), answer["created_at"]))

    def get_answer(self, answer_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT answer_json FROM answers WHERE id=? AND owner_id=?", (answer_id, owner_id)).fetchone()
        return json.loads(row["answer_json"]) if row else None

    def list_answers(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT answer_json FROM answers WHERE owner_id=? ORDER BY created_at DESC LIMIT ?", (owner_id, min(max(limit, 1), 200))).fetchall()
        return [json.loads(row["answer_json"]) for row in rows]

    def delete_document(self, document_id: str, owner_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM documents WHERE id = ? AND owner_id = ?", (document_id, owner_id))
        return cursor.rowcount == 1

    def save_refresh_token(self, token_hash: str, user_id: str, expires_at: int, created_at: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO refresh_tokens(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)", (token_hash, user_id, expires_at, created_at))

    def get_refresh_token(self, token_hash: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM refresh_tokens WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)).fetchone()

    def revoke_refresh_token(self, token_hash: str, revoked_at: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (revoked_at, token_hash))
        return cursor.rowcount == 1

    def save_audit(self, audit_id: str, actor_id: str | None, action: str, request_id: str, metadata: dict[str, Any], created_at: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO audit_logs(id,actor_id,action,request_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)", (audit_id, actor_id, action, request_id, json.dumps(metadata), created_at))

    def save_workspace(self, workspace: Any) -> dict[str, Any]:
        record = as_record(workspace)
        with self.connect() as connection:
            connection.execute("INSERT INTO workspaces(id,owner_id,name,created_at,settings_json) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,settings_json=excluded.settings_json WHERE workspaces.owner_id=excluded.owner_id", (record["id"], record["owner_id"], record["name"], record["created_at"], json.dumps(record.get("settings", {}))))
        return record

    def list_workspaces(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM workspaces WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [{**dict(row), "settings": json.loads(row["settings_json"])} for row in rows]

    def save_research_item(self, item: Any) -> dict[str, Any]:
        record = as_record(item)
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO research_items(id,workspace_id,owner_id,item_type,title,status,source_document_id,data_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (record["id"], record["workspace_id"], record["owner_id"], record["item_type"], record["title"], record.get("status", "active"), record.get("source_document_id"), json.dumps(record.get("data", {})), record["created_at"], record.get("updated_at") or record["created_at"]))
        return record

    def list_research_items(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM research_items WHERE workspace_id = ? AND owner_id = ? ORDER BY updated_at DESC", (workspace_id, owner_id)).fetchall()
        return [{**dict(row), "data": json.loads(row["data_json"])} for row in rows]

    def save_note(self, note: Any) -> dict[str, Any]:
        record = as_record(note)
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO notes(id,workspace_id,owner_id,research_item_id,title,body,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (record["id"], record["workspace_id"], record["owner_id"], record.get("research_item_id"), record.get("title", ""), record["body"], record["created_at"], record.get("updated_at") or record["created_at"]))
        return record

    def list_notes(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM notes WHERE workspace_id = ? AND owner_id = ? ORDER BY updated_at DESC", (workspace_id, owner_id)).fetchall()
        return [dict(row) for row in rows]

    def save_evidence(self, evidence: Any) -> dict[str, Any]:
        record = as_record(evidence)
        with self.connect() as connection:
            connection.execute("INSERT INTO saved_evidence(id,workspace_id,owner_id,evidence_id,snapshot_json,note,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace_id,evidence_id) DO UPDATE SET snapshot_json=excluded.snapshot_json,note=excluded.note WHERE saved_evidence.owner_id=excluded.owner_id", (record["id"], record["workspace_id"], record["owner_id"], record["evidence_id"], json.dumps(record.get("snapshot", {})), record.get("note", ""), record["created_at"]))
        return next(item for item in self.list_saved_evidence(record["workspace_id"], record["owner_id"]) if item["evidence_id"] == record["evidence_id"])

    def list_saved_evidence(self, workspace_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM saved_evidence WHERE workspace_id = ? AND owner_id = ? ORDER BY created_at DESC", (workspace_id, owner_id)).fetchall()
        return [{**dict(row), "snapshot": json.loads(row["snapshot_json"])} for row in rows]

    def save_experiment(self, experiment: Any) -> dict[str, Any]:
        record = as_record(experiment)
        with self.connect() as connection:
            connection.execute("INSERT INTO experiments(id,owner_id,workspace_id,name,dataset,model,hyperparameters_json,notes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET workspace_id=excluded.workspace_id,name=excluded.name,dataset=excluded.dataset,model=excluded.model,hyperparameters_json=excluded.hyperparameters_json,notes=excluded.notes,status=excluded.status,updated_at=excluded.updated_at WHERE experiments.owner_id=excluded.owner_id", (record["id"], record["owner_id"], record.get("workspace_id"), record["name"], record.get("dataset", ""), record.get("model", ""), json.dumps(record.get("hyperparameters", {})), record.get("notes", ""), record.get("status", "created"), record["created_at"], record.get("updated_at") or record["created_at"]))
        return record

    def list_experiments(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM experiments WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)).fetchall()
        return [{**dict(row), "hyperparameters": json.loads(row["hyperparameters_json"])} for row in rows]

    def save_experiment_metric(self, metric_id: str, experiment_id: str, metric_name: str, metric_value: float) -> None:
        with self.connect() as connection:
            # Match the PostgreSQL one-value-per-metric contract without deleting
            # or migrating historical rows. An existing metric is updated in place.
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("UPDATE experiment_metrics SET metric_value=? WHERE experiment_id=? AND metric_name=?", (metric_value, experiment_id, metric_name)).rowcount
            if not changed:
                connection.execute("INSERT INTO experiment_metrics(id,experiment_id,metric_name,metric_value) VALUES(?,?,?,?)", (metric_id, experiment_id, metric_name, metric_value))

    def delete_experiment(self, experiment_id: str, owner_id: str) -> bool:
        with self.connect() as connection:
            result = connection.execute("DELETE FROM experiments WHERE id=? AND owner_id=?", (experiment_id, owner_id))
        return result.rowcount == 1

    def list_experiment_metrics(self, experiment_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM experiment_metrics WHERE experiment_id = ? ORDER BY metric_name", (experiment_id,)).fetchall()
        return [dict(row) for row in rows]

    def save_ingestion_job(self, job: Any) -> dict[str, Any]:
        record = as_record(job)
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO ingestion_jobs(id,owner_id,workspace_id,source,status,input_ref,error,metadata_json,created_at,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (record["id"], record.get("owner_id"), record.get("workspace_id"), record["source"], record.get("status", "queued"), record.get("input_ref", ""), record.get("error", ""), json.dumps(record.get("metadata", {})), record["created_at"], record.get("started_at"), record.get("finished_at")))
        return record

    def list_ingestion_jobs(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM ingestion_jobs"
        params: tuple[Any, ...] = ()
        if owner_id is not None:
            query += " WHERE owner_id = ?"
            params = (owner_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def get_ingestion_job(self, job_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM ingestion_jobs WHERE id = ?"
        params: list[Any] = [job_id]
        if owner_id is not None:
            query += " AND owner_id = ?"
            params.append(owner_id)
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        if row is None:
            return None
        return {**dict(row), "metadata": json.loads(row["metadata_json"])}

    def update_ingestion_job(self, job_id: str, status: str, *, error: str = "", started_at: str | None = None, finished_at: str | None = None) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("UPDATE ingestion_jobs SET status = ?, error = ?, started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at) WHERE id = ?", (status, error, started_at, finished_at, job_id))
        return cursor.rowcount == 1

    def list_audit(self, actor_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_logs"
        params: tuple[Any, ...] = ()
        if actor_id is not None:
            query += " WHERE actor_id = ?"
            params = (actor_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]

    def save_admin_record(self, record_value: Any) -> dict[str, Any]:
        record = as_record(record_value)
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO admin_records(id,actor_id,record_type,subject_id,data_json,created_at) VALUES(?,?,?,?,?,?)", (record["id"], record.get("actor_id"), record["record_type"], record.get("subject_id"), json.dumps(record.get("data", {})), record["created_at"]))
        return record

    def close(self) -> None:
        """SQLite opens short-lived connections; kept for a common lifecycle API."""
        return None
