"""Compute retrieval metrics on the local CyberTrust-QA evidence labels."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.research.metrics import ndcg, reciprocal_rank  # noqa: E402
from app.services import DocumentStore  # noqa: E402
from app.services.query_understanding import understand_query  # noqa: E402
from app.services.retrieval import HybridRetriever  # noqa: E402


def main() -> None:
    data = json.loads((ROOT / "data/evaluation/cybertrust_qa.json").read_text())
    retriever = HybridRetriever(DocumentStore())
    rows = []
    for item in data["items"]:
        expected = set(item["authoritative_evidence"])
        result = retriever.search(item["question"], understand_query(item["question"]), limit=10)
        ranked = [item.document_id for item in result]
        rows.append({"id": item["id"], "recall_at_10": float(bool(expected.intersection(ranked))), "mrr": reciprocal_rank(expected, ranked), "ndcg": ndcg(expected, ranked, 10)})
    output = {"items": rows, "mean_recall_at_10": sum(row["recall_at_10"] for row in rows) / max(1, len(rows)), "mean_mrr": sum(row["mrr"] for row in rows) / max(1, len(rows)), "mean_ndcg": sum(row["ndcg"] for row in rows) / max(1, len(rows)), "note": "Computed from the local corpus and benchmark labels."}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
