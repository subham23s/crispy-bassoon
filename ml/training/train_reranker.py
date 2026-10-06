"""Train a cross-encoder reranker on query/document pairs.

Pair labels must come from an attributed or human-labeled dataset. The script
refuses to synthesize labels and records the dataset checksum in its manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ml.preprocessing.text import load_pair_dataset

ROOT = Path(__file__).resolve().parents[2]


def train(model_name: str, dataset_path: Path, output_dir: Path, epochs: float = 2.0, batch_size: int = 8, seed: int = 42) -> dict[str, Any]:
    try:
        import numpy as np  # type: ignore
        from datasets import Dataset  # type: ignore
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer, TrainingArguments, set_seed  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Reranker training requires torch, transformers, datasets, and accelerate; install backend/requirements-ml.txt plus datasets.") from exc
    rows = load_pair_dataset(dataset_path)
    if len(rows) < 3:
        raise RuntimeError("at least three labeled query/document pairs are required")
    if len({int(row["label"]) for row in rows}) < 2:
        raise RuntimeError("reranker training requires both relevant and non-relevant labels; the current derived dataset contains only positive pairs")
    if any("synthetic" in row and bool(row["synthetic"]) for row in rows):
        raise RuntimeError("synthetic reranker labels are not accepted for a training run; provide attributed or human-labeled pairs")
    ordered = sorted(rows, key=lambda row: hashlib.sha256(f"{row['text']}\n{row['text_pair']}".encode()).hexdigest())
    cut = max(1, int(len(ordered) * 0.8))
    train_rows, test_rows = ordered[:cut], ordered[cut:]
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=2, id2label={0: "NOT_RELEVANT", 1: "RELEVANT"}, label2id={"NOT_RELEVANT": 0, "RELEVANT": 1}, ignore_mismatched_sizes=True)

    def encode(batch: dict[str, list[str]]) -> dict[str, Any]:
        return tokenizer(batch["text"], batch["text_pair"], truncation=True, max_length=512)

    train_ds = Dataset.from_list([{"text": row["text"], "text_pair": row["text_pair"], "labels": int(row["label"])} for row in train_rows]).map(encode, batched=True)
    test_ds = Dataset.from_list([{"text": row["text"], "text_pair": row["text_pair"], "labels": int(row["label"])} for row in test_rows]).map(encode, batched=True) if test_rows else None
    set_seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(output_dir=str(output_dir), learning_rate=2e-5, per_device_train_batch_size=batch_size, per_device_eval_batch_size=batch_size, num_train_epochs=epochs, weight_decay=0.01, eval_strategy="no", save_strategy="epoch", report_to=[], seed=seed)

    def metrics(prediction: Any) -> dict[str, float]:
        values = np.asarray(prediction.predictions).argmax(axis=-1)
        expected = np.asarray(prediction.label_ids)
        return {"accuracy": float((values == expected).mean()) if len(expected) else 0.0}

    trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=test_ds, tokenizer=tokenizer, data_collator=DataCollatorWithPadding(tokenizer), compute_metrics=metrics)
    trainer.train()
    measured = trainer.evaluate(test_ds, metric_key_prefix="test") if test_ds else {}
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    result = {"status": "measured", "model": model_name, "dataset": str(dataset_path.relative_to(ROOT)), "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(), "train_examples": len(train_rows), "test_examples": len(test_rows), "metrics": measured, "output_dir": str(output_dir.relative_to(ROOT)), "note": "No synthetic labels were accepted."}
    (output_dir / "training_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/ml/reranker/query_document_pairs.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/ml/reranker/transformer_model")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train(args.model, args.dataset, args.output_dir, args.epochs, args.batch_size, args.seed), indent=2))


if __name__ == "__main__":
    main()
