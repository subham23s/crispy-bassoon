"""Cross-source contradiction detection using configurable NLI."""
from __future__ import annotations

from itertools import combinations
from typing import Any

from app.models import Evidence
from app.services.retrieval import tokens
from app.verification.nli_verifier import build_verifier


def detect(evidence: list[Evidence], *, provider: str = "auto", model_name: str = "cross-encoder/nli-deberta-v3-base") -> list[dict[str, Any]]:
    verifier = build_verifier(provider=provider, model_name=model_name)
    conflicts: list[dict[str, Any]] = []
    for left, right in combinations(evidence, 2):
        if left.document_id == right.document_id:
            continue
        for left_sentence in left.text.split("."):
            for right_sentence in right.text.split("."):
                if len(tokens(left_sentence)) < 4 or len(tokens(right_sentence)) < 4:
                    continue
                result = verifier.verify(left_sentence, right_sentence)
                if result.label == "CONTRADICTION" and result.scores.get("CONTRADICTION", 0) >= 0.5:
                    conflicts.append({"source_a": left.source, "source_a_url": left.url, "claim_a": left_sentence.strip(), "source_b": right.source, "source_b_url": right.url, "claim_b": right_sentence.strip(), "conflict": "NLI classified the passages as contradictory.", "verification": result.to_dict()})
    return conflicts[:10]
