"""Construct labeled ML/evaluation datasets with explicit provenance labels.

Manual seed examples are authored bootstrap supervision, not official ground
truth. Optional augmentation is marked synthetic and is never mixed silently
with authoritative knowledge records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

from common import DATA_DIR, ensure_data_dirs, read_jsonl, record_artifact, write_json, write_jsonl

INTENTS = ["vulnerability", "threat_intelligence", "malware", "network_security", "web_security", "cloud_security", "cryptography", "digital_forensics", "incident_response", "ai_security", "threat_hunting", "research", "compliance", "general_cybersecurity"]
INTENT_SEED: dict[str, list[str]] = {
    "vulnerability": ["Which versions are affected by this CVE?", "How should a vulnerability with a high CVSS be remediated?"],
    "threat_intelligence": ["What threat actor uses these indicators?", "Which campaign and TTPs are associated with this malware?"],
    "malware": ["How does this ransomware persist?", "What behaviors are documented for the trojan?"],
    "network_security": ["How should firewall telemetry be investigated?", "What does network segmentation mitigate?"],
    "web_security": ["How can an application prevent SSRF?", "What is the defensive impact of an XSS vulnerability?"],
    "cloud_security": ["How should cloud IAM permissions be reduced?", "What controls protect a Kubernetes workload?"],
    "cryptography": ["How does a TLS handshake protect a connection?", "Which properties should a secure hash function have?"],
    "digital_forensics": ["Which disk artifacts support a forensic timeline?", "How should a memory image be preserved for analysis?"],
    "incident_response": ["What are the containment steps for a security incident?", "How should an alert be escalated without overclaiming a breach?"],
    "ai_security": ["How can a RAG system detect prompt injection?", "What is model poisoning in an AI security context?"],
    "threat_hunting": ["How can analysts hunt for suspicious PowerShell?", "Which signals should corroborate a possible attack pattern?"],
    "research": ["Which datasets and metrics are compared across these papers?", "What candidate research gap follows from repeated limitations?"],
    "compliance": ["How does NIST CSF support risk governance?", "Which evidence is useful for a security control audit?"],
    "general_cybersecurity": ["What is the purpose of defense in depth?", "Explain least privilege for a cybersecurity student."],
}
OOD_SEED = [
    ("What is the weather forecast?", "weather"),
    ("Who won the football match?", "sports"),
    ("Solve this quadratic equation.", "mathematics"),
    ("How do I bake sourdough bread?", "cooking"),
    ("What happened in ancient Rome?", "history"),
    ("Recommend a comedy film.", "entertainment"),
    ("How do I optimize a JavaScript loop?", "general_programming"),
]


def _near_duplicate(left: str, right: str) -> bool:
    a, b = set(re.findall(r"[a-z0-9]+", left.lower())), set(re.findall(r"[a-z0-9]+", right.lower()))
    return bool(a and b) and len(a & b) / max(1, len(a | b)) >= 0.82


def _split(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_label: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_label.setdefault(str(row.get("intent", row.get("label", ""))), []).append(row)
    output = {"train": [], "validation": [], "test": []}
    for label, items in sorted(by_label.items()):
        items = sorted(items, key=lambda item: hashlib.sha256(str(item.get("text", "")).encode()).hexdigest())
        n = len(items)
        train_end = max(1, int(n * 0.7))
        validation_end = min(n, train_end + max(1, int(n * 0.15))) if n > 2 else train_end
        output["train"].extend(items[:train_end])
        output["validation"].extend(items[train_end:validation_end])
        output["test"].extend(items[validation_end:])
    return output


def build(augment: bool = False) -> dict[str, int]:
    ensure_data_dirs()
    intent_rows: list[dict[str, Any]] = []
    seen: list[str] = []
    for intent in INTENTS:
        for text in INTENT_SEED[intent]:
            if any(_near_duplicate(text, previous) for previous in seen):
                continue
            seen.append(text)
            intent_rows.append({"text": text, "intent": intent, "source_type": "manual_curated", "source": "CyberSecRA-X bootstrap seed", "synthetic": False, "difficulty": "medium"})
            if augment:
                synthetic = text.replace("How", "In a defensive analysis, how").replace("What", "For a research assistant, what")
                if not any(_near_duplicate(synthetic, previous) for previous in seen):
                    seen.append(synthetic)
                    intent_rows.append({"text": synthetic, "intent": intent, "source_type": "synthetic_augmentation", "source": "CyberSecRA-X template augmentation", "synthetic": True, "difficulty": "medium"})
    intent_dir = DATA_DIR / "ml/intent"
    intent_dir.mkdir(parents=True, exist_ok=True)
    with (intent_dir / "intent_dataset.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "intent", "source_type", "source", "synthetic", "difficulty"])
        writer.writeheader()
        writer.writerows(intent_rows)
    splits = _split(intent_rows)
    write_json(intent_dir / "intent_splits.json", {key: value for key, value in splits.items()})
    record_artifact("intent_dataset", intent_dir / "intent_dataset.csv", records=len(intent_rows), metadata={"classes": INTENTS, "synthetic_rows": sum(bool(row["synthetic"]) for row in intent_rows), "duplicate_policy": "exact and token-Jaccard >= 0.82 removed before split"})

    ood_rows = [{"text": text, "label": "OUT_OF_DOMAIN", "category": category, "source_type": "manual_curated", "source": "CyberSecRA-X bootstrap seed", "synthetic": False} for text, category in OOD_SEED]
    ood_rows.extend({"text": text, "label": "IN_DOMAIN", "category": "cybersecurity", "source_type": "manual_curated", "source": "CyberSecRA-X bootstrap seed", "synthetic": False} for text in ["What is CVE severity?", "How does MITRE ATT&CK support detection?"])
    ood_path = DATA_DIR / "ml/ood/ood_dataset.csv"
    with ood_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["text", "label", "category", "source_type", "source", "synthetic"])
        writer.writeheader()
        writer.writerows(ood_rows)
    record_artifact("ood_dataset", ood_path, records=len(ood_rows))

    entities = list(read_jsonl(DATA_DIR / "normalized/cyber_entities.jsonl"))
    verification_rows = []
    reranker_rows = []
    temporal_rows = []
    for entity in entities:
        description = entity.get("description", "")
        if isinstance(description, str) and description.strip():
            verification_rows.append({"claim": str(description).split(". ")[0], "evidence": description, "label": "ENTAILMENT", "source_type": "derived_authoritative", "source": entity.get("source"), "synthetic": False})
            reranker_rows.append({"query": entity.get("name", ""), "document": description, "relevance": 1, "source_type": "derived_authoritative", "source": entity.get("source"), "synthetic": False})
        if entity.get("created_at") or entity.get("updated_at"):
            temporal_rows.append({"entity_id": entity.get("id"), "question_type": "version_or_date", "publication_date": entity.get("created_at"), "modified_date": entity.get("updated_at"), "source": entity.get("source"), "synthetic": False})
    verification_rows.append({"claim": "The control is required for all systems.", "evidence": "The control is not required for all systems.", "label": "CONTRADICTION", "source_type": "synthetic_controlled", "source": "CyberSecRA-X controlled regression case", "synthetic": True})
    verification_rows.append({"claim": "A value is documented.", "evidence": "No relevant statement is present.", "label": "UNKNOWN", "source_type": "synthetic_controlled", "source": "CyberSecRA-X controlled regression case", "synthetic": True})
    write_jsonl(DATA_DIR / "ml/verification/claim_verification.jsonl", verification_rows)
    write_jsonl(DATA_DIR / "ml/reranker/query_document_pairs.jsonl", reranker_rows)
    write_jsonl(DATA_DIR / "ml/verification/temporal_cases.jsonl", temporal_rows)
    contradiction_path = DATA_DIR / "ml/verification/contradiction_cases.jsonl"
    write_jsonl(contradiction_path, [row for row in verification_rows if row["label"] == "CONTRADICTION"])
    for name, path, rows in (("claim_verification_dataset", DATA_DIR / "ml/verification/claim_verification.jsonl", verification_rows), ("reranker_dataset", DATA_DIR / "ml/reranker/query_document_pairs.jsonl", reranker_rows), ("temporal_dataset", DATA_DIR / "ml/verification/temporal_cases.jsonl", temporal_rows), ("contradiction_dataset", contradiction_path, [row for row in verification_rows if row["label"] == "CONTRADICTION"])):
        record_artifact(name, path, records=len(rows), metadata={"synthetic_rows": sum(bool(row.get("synthetic")) for row in rows)})
    return {"intent": len(intent_rows), "ood": len(ood_rows), "verification": len(verification_rows), "reranker": len(reranker_rows), "temporal": len(temporal_rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--augment", action="store_true", help="add explicitly synthetic template examples")
    args = parser.parse_args()
    print(json.dumps(build(args.augment), indent=2))


if __name__ == "__main__":
    main()
