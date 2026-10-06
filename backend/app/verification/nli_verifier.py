"""Configurable transformer-NLI verifier with an explicit heuristic fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.services.retrieval import STOPWORDS, tokens


class NLIUnavailable(RuntimeError):
    """Raised when the configured transformer backend is not installed/loaded."""


class UnavailableNLI:
    name = "transformer_nli_unavailable"

    def __init__(self, model_name: str, reason: str) -> None:
        self.model_name = model_name
        self.reason = reason

    def verify(self, premise: str, hypothesis: str) -> "NLIResult":
        return NLIResult(
            "UNKNOWN",
            {"ENTAILMENT": 0.0, "CONTRADICTION": 0.0, "UNKNOWN": 1.0},
            self.model_name,
            False,
            f"Transformer NLI was explicitly requested but unavailable: {self.reason}",
        )


@dataclass(frozen=True)
class NLIResult:
    label: str
    scores: dict[str, float]
    model: str
    used_fallback: bool
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "scores": self.scores,
            "model": self.model,
            "used_fallback": self.used_fallback,
            "explanation": self.explanation,
        }


class HeuristicNLI:
    name = "heuristic-overlap-fallback"

    @staticmethod
    def _polarity(text: str) -> int:
        negative = (" not ", " no ", " cannot ", " should not ", " never ", " without ", " absence ")
        lowered = f" {text.lower()} "
        return -1 if any(term in lowered for term in negative) else 1

    def verify(self, premise: str, hypothesis: str) -> NLIResult:
        left = set(tokens(premise)) - STOPWORDS
        right = set(tokens(hypothesis)) - STOPWORDS
        overlap = len(left & right) / max(1, len(right))
        contradiction = overlap >= 0.5 and self._polarity(premise) != self._polarity(hypothesis)
        if contradiction:
            label = "CONTRADICTION"
        elif overlap >= 0.55:
            label = "ENTAILMENT"
        else:
            label = "UNKNOWN"
        scores = {"ENTAILMENT": round(overlap if label == "ENTAILMENT" else 0.0, 4), "CONTRADICTION": round(overlap if label == "CONTRADICTION" else 0.0, 4), "UNKNOWN": round(1.0 - overlap if label == "UNKNOWN" else 0.0, 4)}
        return NLIResult(label, scores, self.name, True, "Heuristic overlap/polarity fallback; not transformer-NLI evidence.")


class TransformerNLI:
    """Lazy Hugging Face sequence-classification NLI backend.

    The model is never downloaded at API startup. Call ``load()`` explicitly or
    run scripts/setup_models.py after reviewing storage/license requirements.
    """

    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base", device: int = -1) -> None:
        self.model_name = model_name
        self.device = device
        self._pipeline: Any = None

    def load(self, *, allow_download: bool = False) -> None:
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
        except ImportError as exc:
            raise NLIUnavailable("transformers is not installed; use the documented optional ML environment") from exc
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, local_files_only=not allow_download)
            model = AutoModelForSequenceClassification.from_pretrained(self.model_name, local_files_only=not allow_download)
            self._pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, device=self.device, top_k=None)
        except Exception as exc:  # model download/config/runtime failures are explicit
            raise NLIUnavailable(f"could not load NLI model {self.model_name}: {exc}") from exc

    def verify(self, premise: str, hypothesis: str) -> NLIResult:
        if self._pipeline is None:
            self.load()
        try:
            raw = self._pipeline({"text": premise, "text_pair": hypothesis}, truncation=True, max_length=512)
            rows = raw[0] if raw and isinstance(raw[0], list) else raw
            scores: dict[str, float] = {}
            for item in rows:
                label = str(item.get("label", "")).upper()
                if "ENTAIL" in label:
                    normalized = "ENTAILMENT"
                elif "CONTRAD" in label:
                    normalized = "CONTRADICTION"
                else:
                    normalized = "UNKNOWN"
                scores[normalized] = max(scores.get(normalized, 0.0), float(item.get("score", 0.0)))
            scores = {key: round(scores.get(key, 0.0), 4) for key in ("ENTAILMENT", "CONTRADICTION", "UNKNOWN")}
            label = max(scores, key=scores.get)
            return NLIResult(label, scores, self.model_name, False, "Transformer sequence-classification NLI result.")
        except Exception as exc:
            raise NLIUnavailable(f"NLI inference failed: {exc}") from exc


@lru_cache(maxsize=8)
def build_verifier(*, provider: str = "auto", model_name: str = "cross-encoder/nli-deberta-v3-base", device: int = -1) -> TransformerNLI | HeuristicNLI | UnavailableNLI:
    if provider == "heuristic":
        return HeuristicNLI()
    if provider in {"transformer", "nli"}:
        verifier = TransformerNLI(model_name, device)
        try:
            verifier.load()
            return verifier
        except NLIUnavailable as exc:
            return UnavailableNLI(model_name, str(exc))
    try:
        verifier = TransformerNLI(model_name, device)
        verifier.load()
        return verifier
    except NLIUnavailable:
        return HeuristicNLI()
