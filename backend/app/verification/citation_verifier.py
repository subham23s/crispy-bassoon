"""Map answer claims to evidence and verify entailment/citation support."""
from __future__ import annotations

from typing import Any
import re

from app.models import ClaimVerification, Evidence
from app.services.retrieval import tokens
from app.verification.nli_verifier import NLIResult, NLIUnavailable, build_verifier


def overlap(a: str, b: str) -> float:
    left, right = set(tokens(a)), set(tokens(b))
    return len(left & right) / max(1, len(left))


def verify_claims_with_nli(answer_claims: list[str], evidence: list[Evidence], *, provider: str = "auto", model_name: str = "cross-encoder/nli-deberta-v3-base") -> list[ClaimVerification]:
    verifier = build_verifier(provider=provider, model_name=model_name)
    results: list[ClaimVerification] = []
    for index, claim in enumerate(answer_claims):
        markers = [int(value) for value in re.findall(r"\[(?:C|E)(\d+)\]", claim)]
        invalid_citations = any(value < 1 or value > len(evidence) for value in markers)
        candidates = [] if invalid_citations else [evidence[value - 1] for value in dict.fromkeys(markers)] if markers else evidence
        hypothesis = re.sub(r"\[(?:C|E)\d+\]", "", claim).strip()
        ranked = sorted(((item, overlap(hypothesis, item.text)) for item in candidates), key=lambda pair: pair[1], reverse=True)
        citations: list[str] = []
        best_result: NLIResult | None = None
        best_evidence: Evidence | None = None
        for item, lexical_score in ranked[:3]:
            try:
                result = verifier.verify(item.text, hypothesis)
            except NLIUnavailable:
                # Explicit transformer mode must fail closed rather than claim
                # a model result; callers can retry with auto/heuristic.
                result = NLIResult("UNKNOWN", {"ENTAILMENT": 0.0, "CONTRADICTION": 0.0, "UNKNOWN": 1.0}, model_name, False, "NLI backend unavailable; claim not verified.")
            if best_result is None or result.scores.get("ENTAILMENT", 0.0) > best_result.scores.get("ENTAILMENT", 0.0):
                best_result, best_evidence = result, item
            if result.label == "ENTAILMENT" and result.scores.get("ENTAILMENT", 0.0) >= 0.5:
                citations.append(item.chunk_id)
        result = best_result or NLIResult("UNKNOWN", {"ENTAILMENT": 0.0, "CONTRADICTION": 0.0, "UNKNOWN": 1.0}, getattr(verifier, "name", "unknown"), True, "No evidence was available.")
        if result.label == "ENTAILMENT" and citations:
            status = "SUPPORTED"
        elif result.label == "CONTRADICTION":
            status = "CONTRADICTED"
        elif result.used_fallback and best_evidence and overlap(hypothesis, best_evidence.text) >= 0.24:
            status = "PARTIALLY_SUPPORTED"
        else:
            status = "UNKNOWN"
        results.append(ClaimVerification(
            claim_id=f"claim-{index + 1}",
            claim=claim,
            status=status,
            support_score=round(result.scores.get("ENTAILMENT", 0.0), 4),
            citation_ids=list(dict.fromkeys(citations[:3])),
            explanation=("Citation marker references missing evidence. " if invalid_citations else "") + f"{result.explanation} Model: {result.model}.",
            verification_engine="heuristic_fallback" if result.used_fallback else ("transformer_nli_unavailable" if result.model == model_name and "unavailable" in result.explanation.lower() else "transformer_nli"),
            model=result.model,
        ))
    return results
