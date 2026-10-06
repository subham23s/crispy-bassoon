"""Graph queries over normalized bootstrap artifacts with provenance."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


class EvidenceGraph:
    def __init__(self, data_dir: Path | None = None, graph_client: Any | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.graph_client = graph_client
        self._signature: tuple[int, int] | None = None
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def _load(self) -> None:
        path = self.data_dir / "graph" / "cyber_graph.json"
        if not path.exists():
            self.nodes, self.edges = {}, []
            return
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self._signature:
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.nodes = {str(node.get("id")): node for node in payload.get("nodes", []) if node.get("id")}
        self.edges = [edge for edge in payload.get("edges", []) if edge.get("source_entity_id") and edge.get("target_entity_id")]
        self._signature = signature

    def search(self, query: str, *, depth: int = 1, limit: int = 50) -> dict[str, Any]:
        depth = max(0, min(int(depth), 3))
        limit = max(1, min(int(limit), 200))
        if not query.strip():
            return {"query": query, "nodes": [], "edges": [], "resolved_edge_count": 0}
        if self.graph_client is not None and getattr(self.graph_client, "available", False):
            try:
                return self._search_live(query, depth, limit)
            except Exception:
                # A live service that fails during a query is explicitly
                # reported as local degraded provenance rather than hidden.
                pass
        self._load()
        needle = query.strip().lower()
        matches = [node for node in self.nodes.values() if needle in str(node.get("id", "")).lower() or needle in str(node.get("name", "")).lower() or needle in str(node.get("source_id", "")).lower()]
        matches.sort(key=lambda node: (str(node.get("source_id", "")).lower() != needle and str(node["id"]).lower() != needle, str(node["id"])))
        ids = dict.fromkeys(str(node["id"]) for node in matches[:limit])
        frontier = set(ids)
        # Each hop expands only the previous frontier. Mutating the frontier
        # inside the edge loop incorrectly traverses an entire connected graph.
        for _ in range(depth):
            next_frontier: set[str] = set()
            for edge in self.edges:
                source, target = str(edge.get("source_entity_id")), str(edge.get("target_entity_id"))
                if source in frontier or target in frontier:
                    for item in (source, target):
                        if item in self.nodes and item not in ids and len(ids) < limit:
                            ids[item] = None
                            next_frontier.add(item)
            frontier = next_frontier
            if not frontier:
                break
        # Return a closed subgraph: every rendered edge has both endpoints.
        selected_edges = []
        seen: set[tuple[str, str, str]] = set()
        for edge in self.edges if depth else []:
            source, target = str(edge.get("source_entity_id")), str(edge.get("target_entity_id"))
            key = (source, target, str(edge.get("relationship_type", edge.get("type", ""))))
            if source in ids and target in ids and key not in seen:
                seen.add(key)
                selected_edges.append(edge)
        selected_edges = selected_edges[:limit * 4]
        return {"query": query, "nodes": [self.nodes[item] for item in ids], "edges": selected_edges, "depth": depth, "provenance": "data/graph/cyber_graph.json generated from normalized official source records", "resolved_edge_count": sum(bool(edge.get("resolved")) for edge in selected_edges)}

    def _search_live(self, query: str, depth: int, limit: int) -> dict[str, Any]:
        rows = self.graph_client.execute("MATCH (n:CyberEntity) WHERE toLower(n.id) CONTAINS toLower($query) OR toLower(n.name) CONTAINS toLower($query) OR toLower(n.source_id) CONTAINS toLower($query) RETURN properties(n) AS node ORDER BY CASE WHEN toLower(n.source_id)=toLower($query) THEN 0 ELSE 1 END, n.id LIMIT $limit", {"query": query.strip(), "limit": limit})
        def unpack(value: dict[str, Any]) -> dict[str, Any]:
            value = dict(value)
            return json.loads(value["record_json"]) if value.get("record_json") else value
        nodes = {str(row["node"]["id"]): unpack(row["node"]) for row in rows}
        frontier = list(nodes)
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for _ in range(depth):
            if not frontier:
                break
            rows = self.graph_client.execute("MATCH (a:CyberEntity)-[r:RELATED]-(b:CyberEntity) WHERE a.id IN $ids RETURN properties(b) AS node, properties(r) AS edge ORDER BY b.id LIMIT $limit", {"ids": frontier, "limit": limit * 4})
            frontier = []
            for row in rows:
                node, edge = unpack(row["node"]), unpack(row["edge"])
                if node["id"] not in nodes and len(nodes) < limit:
                    nodes[node["id"]] = node
                    frontier.append(node["id"])
                key = (str(edge.get("source_entity_id")), str(edge.get("target_entity_id")), str(edge.get("relationship_type")))
                if key[0] in nodes and key[1] in nodes:
                    edges[key] = edge
        selected = list(edges.values())[:limit * 4]
        return {"query": query, "nodes": list(nodes.values()), "edges": selected, "depth": depth, "provenance": "Neo4j normalized source records", "resolved_edge_count": len(selected)}
