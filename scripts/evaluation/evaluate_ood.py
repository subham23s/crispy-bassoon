"""Compute OOD abstention behavior on a small explicit set."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import ResearchPipeline  # noqa: E402
from app.services.query_understanding import understand_query  # noqa: E402


def main() -> None:
    cases = [("What is the capital of France?", True), ("What does MITRE ATT&CK describe?", False), ("Recommend a dessert recipe.", True)]
    rows = []
    for query, expected_ood in cases:
        result = ResearchPipeline().ask(query)
        classified_ood = not understand_query(query).is_in_domain
        rows.append({"query": query, "expected_ood": expected_ood, "classified_ood": classified_ood, "ood_classification_correct": classified_ood == expected_ood, "abstained": result.abstained})
    print(json.dumps({"items": rows, "ood_accuracy": sum(row["ood_classification_correct"] for row in rows) / len(rows), "note": "OOD classification and abstention are reported separately."}, indent=2))


if __name__ == "__main__":
    main()
