"""Train an explicit OOD baseline over the generated labeled OOD dataset."""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.data.common import hardware_profile, record_artifact, utc_now  # noqa: E402


def train(random_state: int = 42) -> dict[str, object]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report, f1_score
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required for train_ood.py; install backend/requirements.txt") from exc
    path = ROOT / "data/ml/ood/ood_dataset.csv"
    if not path.exists():
        raise RuntimeError("OOD dataset is missing; run python scripts/data/build_ml_datasets.py first")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows = sorted(rows, key=lambda row: row["text"])
    cutoff = max(1, int(len(rows) * 0.75))
    train_rows, test_rows = rows[:cutoff], rows[cutoff:]
    model = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)), ("classifier", LogisticRegression(max_iter=1000, random_state=random_state, class_weight="balanced"))])
    model.fit([row["text"] for row in train_rows], [row["label"] for row in train_rows])
    expected = [row["label"] for row in test_rows]
    predicted = model.predict([row["text"] for row in test_rows]).tolist() if test_rows else []
    metrics = {"model": "tfidf-logistic-regression-ood", "trained_at": utc_now(), "train_examples": len(train_rows), "test_examples": len(test_rows), "accuracy": accuracy_score(expected, predicted) if expected else None, "macro_f1": f1_score(expected, predicted, average="macro", zero_division=0) if expected else None, "classification_report": classification_report(expected, predicted, output_dict=True, zero_division=0) if expected else {}, "hardware": hardware_profile(), "warning": "Small bootstrap labels are a baseline, not production OOD ground truth."}
    output_dir = ROOT / "data/ml/ood"
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "ood_model.pkl").open("wb") as handle:
        pickle.dump(model, handle)
    (output_dir / "ood_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    record_artifact("ood_model", output_dir / "ood_model.pkl", records=len(train_rows), metadata={"model": metrics["model"]})
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train(args.random_state), indent=2))


if __name__ == "__main__":
    main()
