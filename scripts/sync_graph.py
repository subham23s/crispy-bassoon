"""Load the existing, provenance-backed graph artifact into configured Neo4j."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings
from app.database.neo4j_adapter import Neo4jAdapter


def main() -> None:
    adapter = Neo4jAdapter(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, timeout=5)
    try:
        if not adapter.available:
            raise SystemExit("Neo4j unavailable; graph was not imported")
        graph = json.loads((settings.data_dir / "graph/cyber_graph.json").read_text(encoding="utf-8"))
        print(json.dumps(adapter.import_graph(graph["nodes"], graph["edges"]), indent=2))
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
