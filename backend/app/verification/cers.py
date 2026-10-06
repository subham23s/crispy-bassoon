"""Project-defined Cyber Evidence Reliability Score configuration."""
from __future__ import annotations

import json
import os
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Any


DEFAULT_WEIGHTS = {"source_authority": 0.22, "relevance": 0.18, "entailment": 0.25, "agreement": 0.15, "recency": 0.10, "retrieval_confidence": 0.10}


@dataclass(frozen=True)
class CERSConfig:
    weights: dict[str, float]
    abstention_threshold: float
    calibration_status: str


def get_config() -> CERSConfig:
    weights = dict(DEFAULT_WEIGHTS)
    raw = os.getenv("CERS_WEIGHTS", "")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                weights.update({key: float(value) for key, value in parsed.items() if key in weights})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("CERS_WEIGHTS must contain numeric component weights") from exc
    if any(not math.isfinite(value) or value < 0 for value in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("CERS weights must be finite, nonnegative, and have a positive sum")
    total = sum(weights.values())
    weights = {key: value / total for key, value in weights.items()}
    threshold = float(os.getenv("CERS_ABSTENTION_THRESHOLD", "0.42"))
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("CERS_ABSTENTION_THRESHOLD must be in [0, 1]")
    status = "pending-human-calibration"
    return CERSConfig(weights, threshold, status)


def calculate(components: dict[str, float]) -> dict[str, Any]:
    config = get_config()
    components = {key: max(0.0, min(1.0, float(components.get(key, 0.0)))) for key in config.weights}
    score = sum(components.get(name, 0.0) * weight for name, weight in config.weights.items())
    result = {
        "name": "CERS",
        "label": "Cyber Evidence Reliability Score",
        "score": round(score, 4),
        "percentage": round(score * 100, 1),
        "components": {name: round(components.get(name, 0.0), 4) for name in config.weights},
        "weights": config.weights,
        "abstention_threshold": config.abstention_threshold,
        "calibration_status": config.calibration_status,
        "methodology": "Project-defined metric combining authority, relevance, claim support, cross-source agreement, recency, and retrieval confidence. It is not a validated probability of truth.",
    }
    path = os.getenv("CERS_CALIBRATION_PATH")
    if path:
        try:
            artifact = json.loads(Path(path).read_text(encoding="utf-8"))
            if artifact.get("status") != "FITTED" or artifact.get("weights") != config.weights or not artifact.get("labels_sha256"):
                raise ValueError("Calibration artifact is not fitted for the active weights")
            from app.verification.calibration import predict
            threshold = float(artifact["abstention_threshold"])
            calibrated = predict(artifact["mapping"], score)
            if not 0 <= threshold <= 1 or not 0 <= calibrated <= 1:
                raise ValueError("Invalid calibration mapping")
            result.update({"calibrated_score": round(calibrated, 4), "abstention_threshold": threshold, "calibration_status": "experimental-human-calibration", "calibration_labels_sha256": artifact["labels_sha256"]})
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            result["calibration_status"] = "invalid-calibration-artifact"
    return result
