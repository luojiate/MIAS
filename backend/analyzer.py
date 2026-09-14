"""Optional vision hook used by POST /upload-image.

The FastAPI app looks for a script (default: vision/main.py) and runs:

    python <script> <image-path>

The script should print a JSON object with outerFat, innerFat, length, and width.
If the script is missing or fails, the API still accepts the upload with zeros.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PLACEHOLDERS = {
    "outerFat": 0.0,
    "innerFat": 0.0,
    "length": 0.0,
    "width": 0.0,
}

BACKEND_DIR = Path(__file__).resolve().parent


def _candidate_scripts() -> list[Path]:
    env_path = os.getenv("MIAS_ANALYZER_SCRIPT")
    names = [
        BACKEND_DIR / "vision" / "main.py",
        BACKEND_DIR / "vision_main.py",
        BACKEND_DIR / "analyze.py",
    ]
    if env_path:
        names.insert(0, Path(env_path))
    return names


def _normalize(data: dict[str, Any]) -> dict[str, float]:
    mapping = {
        "outerFat": ("outerFat", "outer_fat"),
        "innerFat": ("innerFat", "inner_fat"),
        "length": ("length",),
        "width": ("width",),
    }
    result = dict(PLACEHOLDERS)
    for dest, keys in mapping.items():
        for key in keys:
            if key in data and data[key] is not None:
                try:
                    result[dest] = float(data[key])
                    break
                except (TypeError, ValueError):
                    continue
    return result


def analyze_image(image_path: str) -> dict[str, float]:
    script = next((path for path in _candidate_scripts() if path.is_file()), None)
    if script is None:
        return dict(PLACEHOLDERS)
    try:
        completed = subprocess.run(
            [sys.executable, str(script), image_path],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(script.parent),
            check=False,
        )
        if completed.returncode != 0:
            return dict(PLACEHOLDERS)
        stdout = completed.stdout.strip()
        if not stdout:
            return dict(PLACEHOLDERS)
        payload = json.loads(stdout.splitlines()[-1])
        if not isinstance(payload, dict):
            return dict(PLACEHOLDERS)
        return _normalize(payload)
    except Exception:
        return dict(PLACEHOLDERS)
