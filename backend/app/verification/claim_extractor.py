"""Atomic-claim extraction for answer verification."""
from __future__ import annotations

import re

from app.services.retrieval import tokens


def extract_claims(answer_text: str) -> list[str]:
    """Split an answer into candidate atomic claims.

    This intentionally remains deterministic; only the entailment decision is
    delegated to the configurable NLI verifier.
    """
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", answer_text.strip()) if part.strip()]
    return [sentence for sentence in sentences if len(tokens(sentence)) >= 4]
