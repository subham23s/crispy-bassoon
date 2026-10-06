"""Claim-level verification, citation mapping, contradiction detection, and CERS."""
from __future__ import annotations

import re
from itertools import combinations
from typing import Any

from app.models import ClaimVerification, Evidence
from app.services.retrieval import STOPWORDS, tokens


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if part.strip()]


def _overlap(a: str, b: str) -> float:
    left = set(tokens(a)) - STOPWORDS
    right = set(tokens(b)) - STOPWORDS
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / max(1, len(left))


def _polarity(text: str) -> int:
    negative = (" not ", " no ", " absence ", " cannot ", "should not", "doesn't", "isn't", "never", "without")
    lowered = f" {text.lower()} "
    return -1 if any(term in lowered for term in negative) else 1


def _nli_settings() -> tuple[str, str]:
    import os
    return os.getenv("NLI_PROVIDER", "auto"), os.getenv("NLI_MODEL", "cross-encoder/nli-deberta-v3-base")


def detect_contradictions(evidence: list[Evidence]) -> list[dict[str, Any]]:
    from app.verification.contradiction_detector import detect
    provider, model = _nli_settings()
    return detect(evidence, provider=provider, model_name=model)


def verify_claims(answer_text: str, evidence: list[Evidence]) -> list[ClaimVerification]:
    from app.verification.citation_verifier import verify_claims_with_nli
    from app.verification.claim_extractor import extract_claims
    provider, model = _nli_settings()
    return verify_claims_with_nli(extract_claims(answer_text), evidence, provider=provider, model_name=model)


def cers(claims: list[ClaimVerification], evidence: list[Evidence], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    if not claims or not evidence:
        components = {"source_authority": 0.0, "relevance": 0.0, "entailment": 0.0, "agreement": 0.0, "recency": 0.0, "retrieval_confidence": 0.0}
    else:
        components = {
            "source_authority": sum(item.authority_score for item in evidence) / len(evidence),
            "relevance": sum(item.relevance_score for item in evidence) / len(evidence),
            "entailment": sum(item.support_score for item in claims) / len(claims),
            "agreement": max(0.0, 1.0 - min(1.0, len(conflicts) / max(1, len(evidence)))),
            "recency": sum(item.recency_score for item in evidence) / len(evidence),
            "retrieval_confidence": min(1.0, max(item.final_score for item in evidence)),
        }
    from app.verification.cers import calculate
    result = calculate(components)
    engines = sorted({getattr(claim, "verification_engine", "unknown") for claim in claims if getattr(claim, "verification_engine", "unknown")})
    result["verification_engines"] = engines or ["none"]
    result["verification_engine"] = engines[0] if len(engines) == 1 else ("mixed" if engines else "none")
    return result
