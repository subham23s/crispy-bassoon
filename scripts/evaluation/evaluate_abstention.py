"""Measure abstention accuracy for benchmark items explicitly labeled abstention."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import ResearchPipeline  # noqa: E402


def main() -> None:
    data = json.loads((ROOT / "data/evaluation/cybertrust_qa.json").read_text())
    rows = []
    for item in data["items"]:
        expected = item["category"] == "abstention"
        actual = ResearchPipeline().ask(item["question"]).abstained
        rows.append({"id": item["id"], "expected_abstention": expected, "actual_abstention": actual, "correct": expected == actual})
    print(json.dumps({"items": rows, "accuracy": sum(row["correct"] for row in rows) / max(1, len(rows)), "note": "Computed on the current small benchmark only."}, indent=2))


if __name__ == "__main__":
    main()
