"""Persistence-facing records shared by local and production repositories.

These records deliberately contain plain JSON-compatible values.  The API and
background jobs can therefore use the same repository contract regardless of
whether SQLite or PostgreSQL is selected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Workspace:
    id: str
    owner_id: str
    name: str
    created_at: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchItem:
    id: str
    workspace_id: str
    owner_id: str
    item_type: str
    title: str
    status: str = "active"
    source_document_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Note:
    id: str
    workspace_id: str
    owner_id: str
    body: str
    title: str = ""
    research_item_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SavedEvidence:
    id: str
    workspace_id: str
    owner_id: str
    evidence_id: str
    snapshot: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class Experiment:
    id: str
    owner_id: str
    name: str
    workspace_id: str | None = None
    dataset: str = ""
    model: str = ""
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    status: str = "created"
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class IngestionJob:
    id: str
    owner_id: str | None
    workspace_id: str | None
    source: str
    status: str = "queued"
    input_ref: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class AuditLog:
    id: str
    actor_id: str | None
    action: str
    request_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass(frozen=True)
class AdminRecord:
    id: str
    actor_id: str | None
    record_type: str
    subject_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


def as_record(value: Any) -> dict[str, Any]:
    """Convert a persistence dataclass to a repository-ready dictionary."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return dict(value)
