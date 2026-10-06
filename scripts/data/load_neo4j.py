"""Load the generated graph artifact into a configured Neo4j instance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import DATA_DIR


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=DATA_DIR / "graph/cyber_graph.json")
    args = parser.parse_args()
    try:
        from app.config import settings
        from app.database import Neo4jAdapter
    except ImportError as exc:
        raise RuntimeError("backend dependencies are required") from exc
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    adapter = Neo4jAdapter(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, settings.service_connect_timeout)
    if not adapter.available:
        print(json.dumps({"status": "blocked", "reason": adapter.health.reason, "nodes": 0, "edges": 0}, indent=2))
        return
    try:
        adapter.execute("UNWIND $nodes AS node MERGE (n:CyberEntity {id: node.id}) SET n.entity_type=node.entity_type, n.name=node.name, n.source_id=node.source_id, n.source=node.source, n.description=node.description", {"nodes": graph.get("nodes", [])})
        adapter.execute("UNWIND $edges AS edge MATCH (a:CyberEntity {id: edge.source_entity_id}), (b:CyberEntity {id: edge.target_entity_id}) MERGE (a)-[r:RELATED {relationship_type: edge.relationship_type, id: edge.id}]->(b) SET r.source=edge.source, r.evidence=edge.evidence", {"edges": graph.get("edges", [])})
        print(json.dumps({"status": "processed", "nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", [])), "database": "neo4j"}, indent=2))
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
