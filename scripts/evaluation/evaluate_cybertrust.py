"""Run the local CyberTrust-QA benchmark without fabricating metrics."""
from __future__ import annotations

import json
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.research.metrics import exact_match, token_f1  # noqa: E402
from app.services import ResearchPipeline  # noqa: E402


def main() -> None:
    dataset = json.loads((ROOT / "data/evaluation/cybertrust_qa.json").read_text())
    pipeline = ResearchPipeline()
    rows = []
    for item in dataset["items"]:
        answer = pipeline.ask(item["question"])
        rows.append({
            "id": item["id"],
            "category": item["category"],
            "abstained": answer.abstained,
            "cers": answer.cers["score"],
            "claim_support_rate": sum(claim.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"} for claim in answer.claims) / max(1, len(answer.claims)),
            "exact_match": exact_match(item["expected_answer"], answer.answer),
            "token_f1": token_f1(item["expected_answer"], answer.answer),
            "citation_count": len(answer.evidence),
        })
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": dataset["name"],
        "version": dataset["version"],
        "benchmark_sha256": hashlib.sha256((ROOT / "data/evaluation/cybertrust_qa.json").read_bytes()).hexdigest(),
        "corpus_mode": "curated_seed",
        "corpus_documents": len(pipeline.store.documents),
        "corpus_sha256": hashlib.sha256(json.dumps(sorted((doc.document_id, doc.content) for doc in pipeline.store.documents.values()), ensure_ascii=False).encode()).hexdigest(),
        "items": rows,
        "mean_cers": sum(row["cers"] for row in rows) / max(1, len(rows)),
        "abstention_rate": sum(row["abstained"] for row in rows) / max(1, len(rows)),
        "note": "Metrics were computed from this run; they are not hard-coded and are not a claim of external validation.",
    }
    output = ROOT / "data/evaluation/cybertrust_results.json"
    output.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
