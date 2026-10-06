"""Evaluate saved transformer artifacts without fabricating missing results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def evaluate(model_dir: Path, rows: list[dict[str, Any]], *, pair: bool = False) -> dict[str, Any]:
    if not model_dir.exists():
        return {"status": "not_run", "reason": f"model artifact missing: {model_dir}"}
    if not rows:
        return {"status": "not_run", "reason": "No labeled evaluation examples were provided"}
    try:
        from transformers import pipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError("transformers is not installed") from exc
    classifier = pipeline("text-classification", model=str(model_dir), tokenizer=str(model_dir), top_k=None)
    correct = 0
    predictions = []
    for row in rows:
        raw = classifier({"text": row["text"], "text_pair": row["text_pair"]} if pair else row["text"], truncation=True, max_length=512)
        candidates = raw[0] if raw and isinstance(raw[0], list) else raw
        best = max(candidates, key=lambda item: float(item.get("score", 0.0)))
        predicted = str(best.get("label", ""))
        expected = str(row["label"])
        if pair and expected in {"0", "1"}:
            expected = "RELEVANT" if expected == "1" else "NOT_RELEVANT"
        correct += int(predicted == expected)
        predictions.append({"expected": expected, "predicted": predicted, "score": float(best.get("score", 0.0))})
    return {"status": "measured", "examples": len(rows), "accuracy": correct / max(1, len(rows)), "predictions": predictions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--pair", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(json.dumps(evaluate(args.model_dir, rows, pair=args.pair), indent=2))


if __name__ == "__main__":
    main()
