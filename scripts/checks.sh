#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHONPATH=backend python3 -m compileall -q backend scripts
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
npm test --prefix frontend
PYTHONPATH=backend python3 scripts/evaluation/evaluate_cybertrust.py
