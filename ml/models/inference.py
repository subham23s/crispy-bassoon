"""Optional transformer inference adapters with explicit engine reporting."""
from __future__ import annotations

import os
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


class ModelUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Prediction:
    label: str
    score: float
    engine: str
    model: str
    candidates: list[dict[str, Any]]


class TransformerTextClassifier:
    def __init__(self, model_name: str, *, task: str) -> None:
        self.model_name = model_name
        self.task = task
        self._pipeline: Any = None

    def _load(self) -> None:
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
        except ImportError as exc:
            raise ModelUnavailable("transformers is not installed") from exc
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(self.model_name, local_files_only=True)
            self._pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, top_k=None)
        except Exception as exc:
            raise ModelUnavailable(f"could not load {self.model_name}: {exc}") from exc

    def predict(self, text: str) -> Prediction:
        if self._pipeline is None:
            self._load()
        try:
            raw = self._pipeline(text, truncation=True, max_length=512)
            rows = raw[0] if raw and isinstance(raw[0], list) else raw
            candidates = sorted([{"label": str(item.get("label", "")), "score": round(float(item.get("score", 0.0)), 6)} for item in rows], key=lambda item: item["score"], reverse=True)
            best = candidates[0] if candidates else {"label": "UNKNOWN", "score": 0.0}
            label = best["label"]
            if self.task == "ood":
                label = label.upper()
                if label not in {"IN_DOMAIN", "OUT_OF_DOMAIN"}:
                    raise ModelUnavailable("OOD model must declare IN_DOMAIN and OUT_OF_DOMAIN labels")
            return Prediction(label, float(best["score"]), "transformer", self.model_name, candidates)
        except Exception as exc:
            raise ModelUnavailable(f"inference failed for {self.model_name}: {exc}") from exc


class TransformerReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._pipeline: Any = None

    def _load(self) -> None:
        try:
            from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
        except ImportError as exc:
            raise ModelUnavailable("transformers is not installed") from exc
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, local_files_only=True)
            model = AutoModelForSequenceClassification.from_pretrained(self.model_name, local_files_only=True)
            self._pipeline = pipeline("text-classification", model=model, tokenizer=tokenizer, top_k=None)
        except Exception as exc:
            raise ModelUnavailable(f"could not load reranker {self.model_name}: {exc}") from exc

    def score(self, query: str, document: str) -> Prediction:
        if self._pipeline is None:
            self._load()
        try:
            scalar = self._pipeline.model.config.num_labels == 1
            raw = self._pipeline({"text": query, "text_pair": document}, truncation=True, max_length=512, function_to_apply="sigmoid" if scalar else "softmax")
            rows = raw[0] if raw and isinstance(raw[0], list) else raw
            candidates = sorted([{"label": str(item.get("label", "")), "score": round(float(item.get("score", 0.0)), 6)} for item in rows], key=lambda item: item["score"], reverse=True)
            positive_label = os.getenv("RERANKER_RELEVANT_LABEL", "RELEVANT").upper()
            relevant = candidates[0] if scalar and len(candidates) == 1 else next((item for item in candidates if item["label"].upper() == positive_label), None)
            if relevant is None:
                raise ModelUnavailable("Reranker relevance label is unknown; configure RERANKER_RELEVANT_LABEL for this checkpoint")
            score = float(relevant["score"])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ModelUnavailable("Reranker returned an invalid relevance score")
            return Prediction("RELEVANT", score, "transformer_reranker", self.model_name, candidates)
        except Exception as exc:
            raise ModelUnavailable(f"reranker inference failed for {self.model_name}: {exc}") from exc


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


@lru_cache(maxsize=8)
def _classifier(model_name: str, task: str) -> TransformerTextClassifier:
    return TransformerTextClassifier(model_name, task=task)


def intent_classifier(model_name: str | None = None) -> TransformerTextClassifier:
    return _classifier(model_name or _setting("INTENT_MODEL", "data/ml/intent/transformer_model"), "intent")


def ood_classifier(model_name: str | None = None) -> TransformerTextClassifier:
    return _classifier(model_name or _setting("OOD_MODEL", "data/ml/ood/transformer_model"), "ood")


@lru_cache(maxsize=4)
def _reranker(model_name: str) -> TransformerReranker:
    return TransformerReranker(model_name)


def reranker(model_name: str | None = None) -> TransformerReranker:
    return _reranker(model_name or _setting("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
