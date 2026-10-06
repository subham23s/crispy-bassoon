"""Fit an empirical reliability mapping from attributed human annotations only."""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from typing import Any

LABELS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNKNOWN"}


def validate_rows(rows: list[dict[str, Any]]) -> None:
    seen = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"record {index}: expected an object")
        for key in ("claim", "evidence", "source", "category", "annotator_id"):
            if not row.get(key):
                raise ValueError(f"record {index}: {key} is required")
        if row.get("human_label") not in LABELS:
            raise ValueError(f"record {index}: invalid human_label")
        value = row.get("cers_score")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"record {index}: cers_score must be finite and in [0, 1]")
        key = hashlib.sha256(json.dumps([row["claim"], row["evidence"]], sort_keys=True).encode()).hexdigest()
        if key in seen:
            raise ValueError(f"record {index}: duplicate claim/evidence; adjudicate annotations before calibration")
        seen.add(key)
        if row.get("split") not in {"calibration", "evaluation"}:
            raise ValueError(f"record {index}: explicit calibration/evaluation split required")


def fit_isotonic(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Pool-adjacent-violators with equal-score ties pooled before fitting."""
    groups: dict[float, list[float]] = {}
    for row in rows:
        groups.setdefault(float(row["cers_score"]), []).append(float(row["human_label"] == "SUPPORTED"))
    blocks: list[list[float]] = []
    for score, labels in sorted(groups.items()):
        blocks.append([score, score, sum(labels), float(len(labels))])
        while len(blocks) > 1 and blocks[-2][2] / blocks[-2][3] > blocks[-1][2] / blocks[-1][3]:
            right, left = blocks.pop(), blocks.pop()
            blocks.append([left[0], right[1], left[2] + right[2], left[3] + right[3]])
    return {"upper_bounds": [block[1] for block in blocks], "values": [block[2] / block[3] for block in blocks]}


def predict(mapping: dict[str, list[float]], score: float) -> float:
    index = min(bisect.bisect_left(mapping["upper_bounds"], score), len(mapping["values"]) - 1)
    return mapping["values"][index]


def calibrate(rows: list[dict[str, Any]], *, minimum: int = 30, max_risk: float = 0.1) -> dict[str, Any]:
    if not 0 <= max_risk <= 1 or minimum < 2:
        raise ValueError("minimum must be at least 2 and max_risk must be in [0, 1]")
    validate_rows(rows)
    training = [row for row in rows if row["split"] == "calibration"]
    evaluation = [row for row in rows if row["split"] == "evaluation"]
    base = {"schema_version": 1, "human_labeled_examples": len(rows), "calibration_examples": len(training), "evaluation_examples": len(evaluation), "target": "human_label == SUPPORTED", "max_empirical_risk": max_risk, "note": "Empirical human-label calibration, not scientific validation or a guarantee of future risk."}
    if len(training) < minimum or len(evaluation) < minimum:
        return {**base, "status": "CALIBRATION_PENDING", "reason": f"At least {minimum} independent records are required in each split", "metrics": {}}
    if len({row["human_label"] == "SUPPORTED" for row in training}) != 2:
        return {**base, "status": "CALIBRATION_PENDING", "reason": "Calibration split requires both supported and non-supported examples", "metrics": {}}
    mapping = fit_isotonic(training)
    threshold = None
    for candidate in sorted({float(row["cers_score"]) for row in training}):
        accepted = [row for row in training if row["cers_score"] >= candidate]
        risk = sum(row["human_label"] != "SUPPORTED" for row in accepted) / len(accepted)
        if risk <= max_risk:
            threshold = candidate
            break
    if threshold is None:
        return {**base, "status": "CALIBRATION_PENDING", "reason": "No nonempty acceptance set meets the requested empirical risk", "metrics": {}}
    accepted = [row for row in evaluation if row["cers_score"] >= threshold]
    predictions = [predict(mapping, row["cers_score"]) for row in evaluation]
    targets = [float(row["human_label"] == "SUPPORTED") for row in evaluation]
    bins = []
    for index in range(10):
        members = [(p, y) for p, y in zip(predictions, targets) if min(int(p * 10), 9) == index]
        if members:
            bins.append({"bin": index, "count": len(members), "mean_prediction": sum(p for p, _ in members) / len(members), "supported_fraction": sum(y for _, y in members) / len(members)})
    metrics = {"brier_score": sum((p - y) ** 2 for p, y in zip(predictions, targets)) / len(targets), "raw_brier_score": sum((row["cers_score"] - y) ** 2 for row, y in zip(evaluation, targets)) / len(targets), "expected_calibration_error": sum(item["count"] * abs(item["mean_prediction"] - item["supported_fraction"]) for item in bins) / len(targets), "coverage": len(accepted) / len(evaluation), "selective_risk": sum(row["human_label"] != "SUPPORTED" for row in accepted) / len(accepted) if accepted else None, "reliability_bins": bins}
    return {**base, "status": "FITTED", "mapping": mapping, "abstention_threshold": threshold, "metrics": metrics}
