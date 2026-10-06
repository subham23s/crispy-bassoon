"""Bounded defensive agent orchestration.

Agents are ordinary services with narrow responsibilities. They cannot execute
commands, exploit systems, or override policy; orchestration only selects
which evidence service should run for a query.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import QueryUnderstanding


@dataclass(frozen=True)
class AgentPlan:
    agents: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"agents": self.agents, "reason": self.reason}


class AgentOrchestrator:
    """Select bounded analysis responsibilities from query understanding."""

    def plan(self, understanding: QueryUnderstanding) -> AgentPlan:
        if not understanding.is_in_domain:
            return AgentPlan(["OODGuardAgent"], "The query is outside the supported cybersecurity domain.")
        agents = ["RetrievalAgent", "VerificationAgent", "ReportGenerationAgent"]
        if understanding.intent in {"vulnerability", "threat_intelligence", "malware", "threat_hunting"}:
            agents.insert(1, "ThreatIntelligenceAgent" if understanding.intent != "vulnerability" else "VulnerabilityAgent")
        if understanding.intent == "research_literature" or understanding.query_type == "research":
            agents.insert(1, "ResearchAgent")
            agents.append("ResearchGapAgent")
        if understanding.requires_multihop_reasoning:
            agents.insert(-1, "KnowledgeGraphAgent")
        return AgentPlan(list(dict.fromkeys(agents)), "Selected from explicit intent, graph, and research requirements; no unrestricted agent is created.")
