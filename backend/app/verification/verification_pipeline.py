"""Composable claim/citation/contradiction verification pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import ClaimVerification, Evidence
from app.verification.claim_extractor import extract_claims
from app.verification.citation_verifier import verify_claims_with_nli
from app.verification.contradiction_detector import detect


@dataclass
class VerificationOutput:
    claims: list[ClaimVerification]
    contradictions: list[dict[str, Any]]
    provider: str
    model: str
    verification_engines: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"claims": [claim.to_dict() for claim in self.claims], "contradictions": self.contradictions, "provider": self.provider, "model": self.model, "verification_engines": self.verification_engines}


class VerificationPipeline:
    def __init__(self, *, provider: str = "auto", model_name: str = "cross-encoder/nli-deberta-v3-base") -> None:
        self.provider = provider
        self.model_name = model_name

    def verify(self, answer_text: str, evidence: list[Evidence]) -> VerificationOutput:
        claims = extract_claims(answer_text)
        verified = verify_claims_with_nli(claims, evidence, provider=self.provider, model_name=self.model_name)
        contradictions = detect(evidence, provider=self.provider, model_name=self.model_name)
        engines = sorted({claim.verification_engine for claim in verified if claim.verification_engine})
        return VerificationOutput(verified, contradictions, self.provider, self.model_name, engines)
