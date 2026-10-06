"""Execute independently defined A-J ablations with honest unavailable states."""
from __future__ import annotations

import csv
import argparse
import json
import os
import sys
import hashlib
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from app.research.metrics import reciprocal_rank  # noqa: E402
from app.services import DocumentStore, ResearchPipeline  # noqa: E402
from app.services.graph import EvidenceGraph  # noqa: E402
from app.services.llm import get_provider, provider_status  # noqa: E402
from app.services.query_understanding import understand_query  # noqa: E402
from app.services.reranking import rerank  # noqa: E402
from app.services.retrieval import HybridRetriever  # noqa: E402
from app.services.verification import detect_contradictions, verify_claims  # noqa: E402
from app.services.pipeline import PipelineOptions  # noqa: E402

CONFIGS = [
    ("A", "LLM only"), ("B", "Basic RAG"), ("C", "Hybrid RAG"), ("D", "Hybrid RAG + reranker"),
    ("E", "Hybrid + source priority"), ("F", "Hybrid + temporal ranking"), ("G", "Hybrid + knowledge graph"),
    ("H", "Hybrid + citation verification"), ("I", "Hybrid + contradiction detection"), ("J", "Complete configured CyberSecRA-X"),
]


def questions() -> list[dict[str, Any]]:
    return json.loads((ROOT / "data/evaluation/cybertrust_qa.json").read_text(encoding="utf-8")).get("items", [])


def unavailable(reason: str) -> dict[str, Any]:
    return {"status": "not_run", "reason": reason}


def options_for(code: str) -> PipelineOptions:
    if code not in "BCDEFGHIJ":
        raise ValueError(code)
    if code == "J":
        return PipelineOptions(generation=False)
    return PipelineOptions(retrieval_mode="lexical" if code == "B" else "hybrid", reranker=code == "D", source_priority=code == "E", temporal=code == "F", graph=code == "G", citation_verification=code == "H", contradictions=code == "I", reliability=False, generation=False)


def run_feature(code: str, store: DocumentStore, pipeline: ResearchPipeline) -> dict[str, Any]:
    if code == "A":
        status = provider_status()
        if not status.configured:
            return unavailable("LLM_PROVIDER and LLM_API_KEY are not configured")
        provider = get_provider(); outputs = []
        for item in questions():
            text = provider.generate([{"role": "system", "content": "Answer the question without external retrieval; state uncertainty."}, {"role": "user", "content": item["question"]}], temperature=0.0)
            outputs.append({"id": item["id"], "answer": text})
        return {"status": "measured", "items": outputs, "provider": status.provider, "note": "Generated text retained for human scoring; no automated truth score is assigned."}
    options = options_for(code)
    variant = ResearchPipeline(store, options=options)
    variant.retriever = pipeline.retriever  # Same corpus/index for every variant.
    outputs = []
    for item in questions():
        started = time.perf_counter()
        answer = variant.ask(item["question"], limit=10)
        if code == "D" and answer.evidence:
            status = answer.evidence[0].provenance.get("reranker_status", {})
            if status.get("status") != "measured":
                return {**unavailable(f"Cross-encoder unavailable: {status}"), "options": asdict(options)}
        ranked = list(dict.fromkeys(e.document_id for e in answer.evidence))
        expected = set(item.get("authoritative_evidence", []))
        outputs.append({"id": item["id"], "latency_seconds": round(time.perf_counter() - started, 6), "recall_at_10": len(expected.intersection(ranked)) / len(expected) if expected else None, "reciprocal_rank": next((1 / (i + 1) for i, value in enumerate(ranked) if value in expected), 0.0) if expected else None, "abstained": answer.abstained, "cers": answer.cers["score"] if options.reliability else None, "graph_edges": sum(len(e.provenance.get("graph_relationships", [])) for e in answer.evidence), "answer": answer.to_dict()})
    if not outputs:
        return unavailable("The benchmark contains no questions")
    measured = [row for row in outputs if row["recall_at_10"] is not None]
    result = {"status": "measured", "options": asdict(options), "items": outputs, "mean_recall_at_10": sum(row["recall_at_10"] for row in measured) / len(measured) if measured else None, "mean_reciprocal_rank": sum(row["reciprocal_rank"] for row in measured) / len(measured) if measured else None, "abstention_rate": sum(row["abstained"] for row in outputs) / len(outputs)}
    if options.reliability:
        result["mean_cers"] = sum(row["cers"] for row in outputs) / len(outputs)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="Print configuration statuses; full results are still saved to disk")
    args = parser.parse_args()
    store = DocumentStore(include_bootstrap=True)
    pipeline = ResearchPipeline(store)
    rows = []
    for code, name in CONFIGS:
        try:
            result = run_feature(code, store, pipeline)
        except Exception as exc:
            result = unavailable(f"execution failed: {type(exc).__name__}: {exc}")
        rows.append({"configuration": code, "name": name, **result})
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "benchmark_sha256": hashlib.sha256((ROOT / "data/evaluation/cybertrust_qa.json").read_bytes()).hexdigest(), "corpus_documents": len(store.documents), "provider": provider_status().__dict__, "rows": rows, "note": "B is lexical; C is the hybrid baseline; D-I each add exactly one component to C (not cumulative). J enables all configured components. B-J use the same deterministic evidence generator to isolate retrieval/verification changes. NOT_RUN rows contain no metrics. Unlabeled claim support is not ground-truth accuracy."}
    output_dir = ROOT / "data/evaluation"; output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ablation_results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = ["configuration", "name", "status", "mean_recall_at_10", "mean_cers", "abstention_rate", "reason"]
    with (output_dir / "ablation_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    markdown = ["# CyberSecRA-X A-J ablation report", "", report["note"], "", "| Configuration | Status | Key metrics | Reason |", "|---|---|---|---|"]
    for row in rows:
        metrics = ", ".join(f"{key}={value}" for key, value in row.items() if key.startswith("mean_") or key.endswith("_rate"))
        markdown.append(f"| {row['configuration']} {row['name']} | {row['status']} | {metrics} | {row.get('reason', '')} |")
    (output_dir / "ablation_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({"generated_at": report["generated_at"], "corpus_documents": report["corpus_documents"], "rows": [{key: value for key, value in row.items() if key != "items"} for row in rows]} if args.summary else report, indent=2))


if __name__ == "__main__":
    main()
