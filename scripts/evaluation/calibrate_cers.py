"""Calibrate project-defined CERS only from human-labeled records.

Expected JSONL schema: claim, evidence, human_label, source, category. An
optional cers_score field permits score calibration metrics; without it the
script reports label distribution and keeps calibration pending.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.verification.calibration import calibrate
LABELS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNKNOWN"}


def load(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return rows, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {number}: expected a JSON object")
            continue
        missing = [key for key in ("claim", "evidence", "human_label", "source", "category") if not row.get(key)]
        if missing:
            errors.append(f"line {number}: missing {missing}")
            continue
        if row.get("human_label") not in LABELS:
            errors.append(f"line {number}: invalid human_label {row.get('human_label')}")
            continue
        rows.append(row)
    return rows, errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, default=ROOT / "data/ml/verification/cers_human_labels.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation/cers_calibration.json")
    parser.add_argument("--minimum-per-split", type=int, default=30)
    parser.add_argument("--max-risk", type=float, default=0.1)
    args = parser.parse_args()
    rows, errors = load(args.labels)
    result: dict[str, Any] = {
        "status": "CALIBRATION_PENDING",
        "human_labeled_examples": len(rows),
        "label_distribution": dict(Counter(row["human_label"] for row in rows)),
        "errors": errors,
        "metrics": {},
        "note": "CERS remains project-defined and is not a scientifically validated probability. No metric is computed without complete human labels and CERS scores.",
    }
    if rows and not errors:
        try:
            result.update(calibrate(rows, minimum=args.minimum_per_split, max_risk=args.max_risk))
        except ValueError as exc:
            errors.append(str(exc))
    if args.labels.exists():
        result["labels_sha256"] = hashlib.sha256(args.labels.read_bytes()).hexdigest()
    from app.verification.cers import get_config
    result["weights"] = get_config().weights
    result["errors"] = errors
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
