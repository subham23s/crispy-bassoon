"""Optional Neo4j driver lifecycle and connectivity checks."""
from __future__ import annotations

import time
import json
from typing import Any

from .health import ServiceHealth, unavailable


NEO4J_SCHEMA: tuple[str, ...] = (
    "CREATE CONSTRAINT cyber_entity_id IF NOT EXISTS FOR (entity:CyberEntity) REQUIRE entity.id IS UNIQUE",
    "CREATE INDEX cyber_entity_name IF NOT EXISTS FOR (entity:CyberEntity) ON (entity.name)",
    "CREATE INDEX cyber_entity_type IF NOT EXISTS FOR (entity:CyberEntity) ON (entity.entity_type)",
)


class Neo4jAdapter:
    def __init__(self, uri: str, username: str, password: str, timeout: float = 0.5) -> None:
        self.uri = uri.strip()
        self.username = username
        self.password = password
        self.timeout = timeout
        self._driver: Any = None
        self.health = self._initial_health()

    def _initial_health(self) -> ServiceHealth:
        if not self.uri:
            return unavailable("neo4j", False, "NEO4J_URI is not configured")
        if not self.username or not self.password:
            return unavailable("neo4j", True, "NEO4J_USERNAME and NEO4J_PASSWORD are required")
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError:
            return unavailable("neo4j", True, "neo4j package is not installed")
        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password), connection_timeout=self.timeout)
            started = time.monotonic()
            self._driver.verify_connectivity()
            self.initialize()
            self.health = ServiceHealth("neo4j", True, True, "ready", latency_ms=round((time.monotonic() - started) * 1000, 2))
        except Exception as exc:
            self.health = unavailable("neo4j", True, f"Neo4j initialization failed: {type(exc).__name__}: {exc}")
            self.close()
        return self.health

    def initialize(self) -> None:
        """Create idempotent graph constraints and lookup indexes."""
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not initialized")
        with self._driver.session() as session:
            for statement in NEO4J_SCHEMA:
                session.run(statement).consume()

    def import_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], batch_size: int = 500) -> dict[str, int]:
        """Idempotently load attributed normalized nodes and resolved edges."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        ids = {str(node["id"]) for node in nodes}
        resolved = [edge for edge in edges if str(edge.get("source_entity_id")) in ids and str(edge.get("target_entity_id")) in ids]
        for start in range(0, len(nodes), batch_size):
            rows = [{"id": str(node["id"]), "name": str(node.get("name", "")), "source_id": str(node.get("source_id", "")), "entity_type": str(node.get("entity_type", "")), "source": str(node.get("source", "")), "record_json": json.dumps(node)} for node in nodes[start:start + batch_size]]
            self.execute("UNWIND $rows AS row MERGE (n:CyberEntity {id: row.id}) SET n += row", {"rows": rows})
        for start in range(0, len(resolved), batch_size):
            rows = [{"source_entity_id": edge["source_entity_id"], "target_entity_id": edge["target_entity_id"], "relationship_type": edge.get("relationship_type", "related"), "record_json": json.dumps(edge), "resolved": True} for edge in resolved[start:start + batch_size]]
            self.execute("UNWIND $rows AS row MATCH (a:CyberEntity {id: row.source_entity_id}), (b:CyberEntity {id: row.target_entity_id}) MERGE (a)-[r:RELATED {relationship_type: row.relationship_type}]->(b) SET r += row", {"rows": rows})
        return {"nodes_upserted": len(nodes), "edges_upserted": len(resolved), "unresolved_edges_skipped": len(edges) - len(resolved)}

    @property
    def available(self) -> bool:
        return self.health.available and self._driver is not None

    def health_check(self) -> ServiceHealth:
        if self._driver is None:
            return self.health
        try:
            started = time.monotonic()
            self._driver.verify_connectivity()
            self.initialize()
            self.health = ServiceHealth("neo4j", True, True, "ready", latency_ms=round((time.monotonic() - started) * 1000, 2))
        except Exception as exc:
            self.health = unavailable("neo4j", True, f"Neo4j health check failed: {type(exc).__name__}: {exc}")
        return self.health

    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not self.available:
            raise RuntimeError("Neo4j is unavailable; graph operation was not performed")
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
