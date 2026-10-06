"""Train the reproducible TF-IDF + logistic-regression intent baseline."""
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


def _read_split(path: Path, name: str) -> tuple[list[str], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(name, [])
    return [row["text"] for row in rows], [row["intent"] for row in rows]


def train(random_state: int = 42) -> dict[str, object]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report, f1_score
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required for train_intent.py; install backend/requirements.txt") from exc
    split_path = ROOT / "data/ml/intent/intent_splits.json"
    if not split_path.exists():
        raise RuntimeError("intent dataset is missing; run python scripts/data/build_ml_datasets.py first")
    train_x, train_y = _read_split(split_path, "train")
    splits = json.loads(split_path.read_text(encoding="utf-8"))
    test_x = [row["text"] for row in splits.get("test", [])]
    test_y = [row["intent"] for row in splits.get("test", [])]
    pipeline = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)), ("classifier", LogisticRegression(max_iter=1000, random_state=random_state, class_weight="balanced"))])
    pipeline.fit(train_x, train_y)
    predictions = pipeline.predict(test_x).tolist() if test_x else []
    metrics = {
        "model": "tfidf-logistic-regression",
        "trained_at": utc_now(),
        "train_examples": len(train_x),
        "test_examples": len(test_x),
        "accuracy": accuracy_score(test_y, predictions) if test_y else None,
        "macro_f1": f1_score(test_y, predictions, average="macro", zero_division=0) if test_y else None,
        "classification_report": classification_report(test_y, predictions, output_dict=True, zero_division=0) if test_y else {},
        "hardware": hardware_profile(),
        "warning": "Small bootstrap labels are a baseline, not production ground truth.",
    }
    output_dir = ROOT / "data/ml/intent"
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "intent_model.pkl").open("wb") as handle:
        pickle.dump(pipeline, handle)
    (output_dir / "intent_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "label_mapping.json").write_text(json.dumps({label: index for index, label in enumerate(sorted(set(train_y)))}, indent=2), encoding="utf-8")
    record_artifact("intent_model", output_dir / "intent_model.pkl", records=len(train_x), metadata={"model": metrics["model"]})
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train(args.random_state), indent=2))


if __name__ == "__main__":
    main()
