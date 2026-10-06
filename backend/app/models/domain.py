"""Domain objects shared by the API and evidence pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Document:
    document_id: str
    title: str
    source: str
    source_type: str
    url: str = ""
    author: str = ""
    publication_date: str = ""
    update_date: str = ""
    version: str = ""
    authority_score: float = 0.0
    language: str = "en"
    tags: list[str] = field(default_factory=list)
    checksum: str = ""
    ingestion_timestamp: str = field(default_factory=now_iso)
    content: str = ""
    security_flags: list[str] = field(default_factory=list)
    extraction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    page_number: int | None = None
    section: str = ""
    source: str = ""
    publication_date: str = ""
    url: str = ""
    version: str = ""
    ordinal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryUnderstanding:
    raw_query: str
    intent: str
    domain: str
    complexity: str
    language: str
    entities: list[dict[str, str]]
    query_type: str
    requires_temporal_reasoning: bool
    requires_multihop_reasoning: bool
    is_in_domain: bool
    out_of_domain_reason: str = ""
    classification_engine: str = "deterministic_keywords"
    ood_engine: str = "deterministic_keywords"
    expanded_queries: list[str] = field(default_factory=list)
    subqueries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    chunk_id: str
    document_id: str
    title: str
    text: str
    source: str
    source_type: str
    url: str
    page_number: int | None
    section: str
    authority_score: float
    relevance_score: float
    recency_score: float
    graph_score: float
    final_score: float
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimVerification:
    claim_id: str
    claim: str
    status: str
    support_score: float
    citation_ids: list[str]
    explanation: str
    verification_engine: str = "unknown"
    model: str = ""
    contradictions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Answer:
    answer_id: str
    query: str
    answer: str
    mode: str
    created_at: str
    understanding: QueryUnderstanding
    evidence: list[Evidence]
    claims: list[ClaimVerification]
    cers: dict[str, Any]
    abstained: bool
    limitations: list[str]
    timeline: list[dict[str, Any]] = field(default_factory=list)
    related_entities: list[dict[str, str]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    agent_plan: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Answer:
        """Restore an answer snapshot written by the repository."""
        values = dict(data)
        values["understanding"] = QueryUnderstanding(**values["understanding"])
        values["evidence"] = [Evidence(**item) for item in values["evidence"]]
        values["claims"] = [ClaimVerification(**item) for item in values["claims"]]
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_id": self.answer_id,
            "query": self.query,
            "answer": self.answer,
            "mode": self.mode,
            "created_at": self.created_at,
            "understanding": self.understanding.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "claims": [item.to_dict() for item in self.claims],
            "cers": self.cers,
            "abstained": self.abstained,
            "limitations": self.limitations,
            "timeline": self.timeline,
            "related_entities": self.related_entities,
            "conflicts": self.conflicts,
            "agent_plan": self.agent_plan,
        }
