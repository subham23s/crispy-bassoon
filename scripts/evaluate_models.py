"""Evaluate trained intent/OOD artifacts without inventing missing metrics."""
from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def evaluate_intent() -> dict[str, object]:
    model_path = ROOT / "data/ml/intent/intent_model.pkl"
    split_path = ROOT / "data/ml/intent/intent_splits.json"
    if not model_path.exists() or not split_path.exists():
        return {"status": "not_trained", "reason": "run scripts/build_ml_datasets.py and scripts/train_intent.py"}
    model = pickle.loads(model_path.read_bytes())
    rows = json.loads(split_path.read_text(encoding="utf-8")).get("test", [])
    expected = [row["intent"] for row in rows]
    predicted = model.predict([row["text"] for row in rows]).tolist() if rows else []
    correct = sum(a == b for a, b in zip(expected, predicted))
    return {"status": "measured", "examples": len(rows), "accuracy": correct / max(1, len(rows)), "predictions": [{"text": row["text"], "expected": exp, "predicted": pred} for row, exp, pred in zip(rows, expected, predicted)]}


def evaluate_ood() -> dict[str, object]:
    model_path = ROOT / "data/ml/ood/ood_model.pkl"
    dataset = ROOT / "data/ml/ood/ood_dataset.csv"
    if not model_path.exists() or not dataset.exists():
        return {"status": "not_trained", "reason": "run scripts/build_ml_datasets.py and scripts/train_ood.py"}
    model = pickle.loads(model_path.read_bytes())
    with dataset.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    predicted = model.predict([row["text"] for row in rows]).tolist()
    correct = sum(row["label"] == pred for row, pred in zip(rows, predicted))
    return {"status": "measured", "examples": len(rows), "accuracy": correct / max(1, len(rows)), "predictions": [{"text": row["text"], "expected": row["label"], "predicted": pred} for row, pred in zip(rows, predicted)]}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    print(json.dumps({"intent": evaluate_intent(), "ood": evaluate_ood(), "note": "Metrics are actual outputs of the local baseline and small bootstrap labels."}, indent=2))


if __name__ == "__main__":
    main()
