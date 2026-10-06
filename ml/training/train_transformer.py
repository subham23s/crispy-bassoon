"""Train a Hugging Face transformer classifier from CyberSecRA-X datasets.

This script requires the optional ML environment and downloads only the model
specified by the operator. It never reports metrics when training/evaluation
cannot actually run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ml.preprocessing.text import read_json_splits, read_csv_rows

ROOT = Path(__file__).resolve().parents[2]


def train(task: str, model_name: str, output_dir: Path, epochs: float = 2.0, batch_size: int = 8, seed: int = 42) -> dict[str, Any]:
    try:
        import numpy as np  # type: ignore
        import torch  # type: ignore
        from datasets import Dataset  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
            set_seed,
        )
    except ImportError as exc:
        raise RuntimeError("Transformer training requires torch, transformers, datasets, and evaluate-compatible dependencies; install backend/requirements-ml.txt plus datasets.") from exc

    if task == "intent":
        split_path = ROOT / "data/ml/intent/intent_splits.json"
        if not split_path.exists():
            raise RuntimeError("intent splits missing; run scripts/data/build_ml_datasets.py")
        raw = read_json_splits(split_path, "intent")
    elif task == "ood":
        rows = read_csv_rows(ROOT / "data/ml/ood/ood_dataset.csv")
        if not rows:
            raise RuntimeError("OOD dataset missing; run scripts/data/build_ml_datasets.py")
        ordered = sorted(rows, key=lambda row: row["text"])
        cut = max(1, int(len(ordered) * 0.75))
        raw = {"train": [{"text": row["text"], "label": row["label"]} for row in ordered[:cut]], "validation": [], "test": [{"text": row["text"], "label": row["label"]} for row in ordered[cut:]]}
    else:
        raise ValueError("task must be intent or ood")

    labels = sorted({str(row["label"]) for rows in raw.values() for row in rows})
    label_to_id = {label: index for index, label in enumerate(labels)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    datasets = {split: Dataset.from_list([{**row, "labels": label_to_id[str(row["label"])]} for row in rows]) for split, rows in raw.items() if rows}
    set_seed(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=len(labels), label2id=label_to_id, id2label={str(k): v for k, v in id_to_label.items()})

    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=512)

    tokenized = {split: dataset.map(tokenize, batched=True) for split, dataset in datasets.items()}
    set_seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(output_dir),
        learning_rate=2e-5,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        num_train_epochs=epochs,
        weight_decay=0.01,
        eval_strategy="epoch" if "validation" in tokenized else "no",
        save_strategy="epoch",
        load_best_model_at_end="validation" in tokenized,
        metric_for_best_model="accuracy" if "validation" in tokenized else None,
        report_to=[],
        seed=seed,
    )

    def metrics(prediction: Any) -> dict[str, float]:
        values = np.asarray(prediction.predictions).argmax(axis=-1)
        expected = np.asarray(prediction.label_ids)
        return {"accuracy": float((values == expected).mean()) if len(expected) else 0.0}

    trainer = Trainer(model=model, args=args, train_dataset=tokenized["train"], eval_dataset=tokenized.get("validation"), tokenizer=tokenizer, data_collator=DataCollatorWithPadding(tokenizer), compute_metrics=metrics)
    trainer.train()
    test_metrics = trainer.evaluate(tokenized["test"], metric_key_prefix="test") if "test" in tokenized and len(tokenized["test"]) else {}
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    result = {"status": "measured", "task": task, "model": model_name, "labels": labels, "output_dir": str(output_dir.relative_to(ROOT)), "test_metrics": test_metrics, "seed": seed, "note": "Metrics are from the executed transformer run over the current labeled dataset."}
    (output_dir / "training_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("intent", "ood"), required=True)
    parser.add_argument("--model", default="distilbert-base-uncased")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = args.output_dir or ROOT / "data/ml" / args.task / "transformer_model"
    print(json.dumps(train(args.task, args.model, output, args.epochs, args.batch_size, args.seed), indent=2))


if __name__ == "__main__":
    main()
