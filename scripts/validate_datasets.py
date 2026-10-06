"""Validate bootstrap ML/evaluation artifacts and data leakage boundaries."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate() -> dict[str, object]:
    intent_path = DATA_DIR / "ml/intent/intent_dataset.csv"
    ood_path = DATA_DIR / "ml/ood/ood_dataset.csv"
    intent = _read_csv(intent_path)
    ood = _read_csv(ood_path)
    errors: list[str] = []
    warnings: list[str] = []
    texts = [row.get("text", "").strip().lower() for row in intent]
    if len(texts) != len(set(texts)):
        errors.append("intent dataset contains exact duplicate text")
    classes = sorted({row.get("intent", "") for row in intent})
    if len(classes) < 14:
        warnings.append(f"intent dataset currently has {len(classes)} classes; expected 14")
    synthetic_intent = sum(row.get("synthetic", "").lower() == "true" for row in intent)
    if synthetic_intent and not all(row.get("source_type") == "synthetic_augmentation" for row in intent if row.get("synthetic", "").lower() == "true"):
        errors.append("synthetic intent rows do not carry synthetic_augmentation source_type")
    if any(row.get("label") not in {"IN_DOMAIN", "OUT_OF_DOMAIN"} for row in ood):
        errors.append("OOD dataset contains an unknown label")
    result = {"status": "valid" if not errors else "invalid", "errors": errors, "warnings": warnings, "intent_examples": len(intent), "intent_classes": classes, "intent_synthetic": synthetic_intent, "ood_examples": len(ood)}
    output = DATA_DIR / "ml/dataset_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    argparse.ArgumentParser().parse_args()
    result = validate()
    raise SystemExit(0 if result["status"] == "valid" else 2)


if __name__ == "__main__":
    main()
