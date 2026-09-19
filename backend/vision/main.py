#!/usr/bin/env python3
"""CLI entry for FastAPI analyzer subprocess (prints JSON metrics)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python vision/main.py` with backend as cwd
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from vision.infer import analyze


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: main.py <image-path>"}), file=sys.stderr)
        return 1
    payload = analyze(Path(sys.argv[1]))
    # Keep only fields the API stores in session
    print(json.dumps({
        "outerFat": payload["outerFat"],
        "innerFat": payload["innerFat"],
        "length": payload["length"],
        "width": payload["width"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
