"""Optional cross-encoder reranking with explicit degraded status."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.models import Evidence


def rerank(query: str, evidence: list[Evidence]) -> tuple[list[Evidence], dict[str, Any]]:
    provider = os.getenv("RERANKER_PROVIDER", "none").lower()
    configured_model = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    if provider in {"", "none", "disabled"} or not evidence:
        return evidence, {"provider": provider or "none", "status": "not_configured", "model": configured_model}
    if provider == "auto":
        local = Path(os.getenv("RERANKER_MODEL", "data/ml/reranker/transformer_model"))
        if not local.exists():
            return evidence, {"provider": provider, "status": "unavailable_local_model_missing", "model": str(local)}
    try:
        from ml.models.inference import ModelUnavailable, reranker as get_reranker
        adapter = get_reranker(configured_model)
        # Publish a reranking only if every candidate was actually scored.
        predictions = [adapter.score(query, item.text) for item in evidence]
        scored: list[tuple[float, Evidence]] = []
        for item, prediction in zip(evidence, predictions):
            value = max(0.0, min(1.0, prediction.score))
            item.provenance["reranker"] = {"engine": prediction.engine, "model": prediction.model, "score": value}
            item.final_score = round(0.6 * item.final_score + 0.4 * value, 6)
            scored.append((item.final_score, item))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)], {"provider": provider, "status": "measured", "model": configured_model, "engine": "transformer_cross_encoder"}
    except Exception as exc:
        return evidence, {"provider": provider, "status": "unavailable", "model": configured_model, "error": f"{type(exc).__name__}: {exc}"}
