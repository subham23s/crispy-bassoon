"""Run contradiction detector on an explicitly constructed evidence pair."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.models import Evidence  # noqa: E402
from app.services.verification import detect_contradictions  # noqa: E402


def main() -> None:
    left = Evidence('a', 'doc-a', 'A', 'The control is required for all systems.', 'Source A', 'official', 'https://a.invalid', None, '', .9, .8, .8, 0, .8)
    right = Evidence('b', 'doc-b', 'B', 'The control is not required for all systems.', 'Source B', 'official', 'https://b.invalid', None, '', .9, .8, .8, 0, .8)
    result = detect_contradictions([left, right])
    print(json.dumps({'conflicts': result, 'detected': bool(result), 'note': 'Synthetic regression pair only; not a source finding.'}, indent=2))


if __name__ == '__main__':
    main()
