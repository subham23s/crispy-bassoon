"""Build a provenance-preserving graph artifact from official normalized records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import DATA_DIR, ensure_data_dirs, read_jsonl, record_artifact, write_json


def build() -> dict[str, int]:
    ensure_data_dirs()
    entity_path = DATA_DIR / "normalized/cyber_entities.jsonl"
    relationship_path = DATA_DIR / "normalized/cyber_relationships.jsonl"
    nodes = list(read_jsonl(entity_path))
    node_keys = {node.get("id") for node in nodes}
    edges = []
    for edge in read_jsonl(relationship_path):
        source = str(edge.get("source_entity_id", ""))
        target = str(edge.get("target_entity_id", ""))
        # STIX IDs do not always equal normalized entity IDs. Preserve every
        # official edge with an explicit resolution flag; never invent a
        # crosswalk merely to make the graph look connected.
        edges.append({**edge, "resolved": source in node_keys and target in node_keys})
    output = DATA_DIR / "graph/cyber_graph.json"
    write_json(output, {"schema_version": "1.0", "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "nodes": nodes, "edges": edges})
    record_artifact("cyber_graph", output, records=len(nodes) + len(edges), metadata={"nodes": len(nodes), "edges": len(edges)})
    return {"nodes": len(nodes), "edges": len(edges)}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
