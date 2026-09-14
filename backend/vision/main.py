#!/usr/bin/env python3
"""Stub image-analysis script. Replace this with a real vision model.

Prints a JSON object to stdout so the FastAPI upload route can store metrics
in the session. Uses image dimensions / brightness as stand-in measurements.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def analyze(path: Path) -> dict[str, float]:
    try:
        from PIL import Image, ImageStat
    except Exception:
        return {"outerFat": 0.0, "innerFat": 0.0, "length": 0.0, "width": 0.0}

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width_px, height_px = rgb.size
        stats = ImageStat.Stat(rgb)
        brightness = sum(stats.mean) / 3.0
        # Scale pixels to a compact numeric readout similar to the old client.
        length = round(height_px / 10.0, 2)
        width = round(width_px / 10.0, 2)
        outer = round((brightness / 255.0) * 18.0, 2)
        inner = round((brightness / 255.0) * 9.0, 2)
        return {
            "outerFat": outer,
            "innerFat": inner,
            "length": length,
            "width": width,
        }


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: main.py <image-path>"}), file=sys.stderr)
        return 1
    payload = analyze(Path(sys.argv[1]))
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
