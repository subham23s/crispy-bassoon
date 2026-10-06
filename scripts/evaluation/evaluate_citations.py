"""Compute claim support and citation coverage from actual pipeline answers."""
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
        answer = ResearchPipeline().ask(item["question"])
        claims = answer.claims
        supported = [claim for claim in claims if claim.status == "SUPPORTED"]
        cited = [claim for claim in claims if claim.citation_ids]
        rows.append({"id": item["id"], "claim_support_rate": len(supported) / max(1, len(claims)), "citation_coverage": len(cited) / max(1, len(claims)), "claims": len(claims)})
    print(json.dumps({"items": rows, "note": "Heuristic claim verification over the local evidence baseline; not human validation."}, indent=2))


if __name__ == "__main__":
    main()
