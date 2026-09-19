"""Vision hook for POST /upload-image — ONNX EfficientTransUNet + overlay."""
from __future__ import annotations

import json
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


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "outerFat": ("outerFat", "outer_fat"),
        "innerFat": ("innerFat", "inner_fat"),
        "length": ("length",),
        "width": ("width",),
    }
    result: dict[str, Any] = dict(PLACEHOLDERS)
    for dest, keys in mapping.items():
        for key in keys:
            if key in data and data[key] is not None:
                try:
                    result[dest] = float(data[key])
                    break
                except (TypeError, ValueError):
                    continue
    for key in ("overlay_file", "inner_mask_file", "outer_mask_file"):
        if key in data and data[key]:
            result[key] = str(data[key])
    return result


def analyze_image(image_path: str, out_dir: str | None = None) -> dict[str, Any]:
    try:
        from vision.infer import analyze

        return _normalize(analyze(image_path, out_dir=out_dir))
    except Exception as exc:
        print(f"[analyzer] in-process failed: {exc!r}", file=sys.stderr)

    script = BACKEND_DIR / "vision" / "main.py"
    if not script.is_file():
        return dict(PLACEHOLDERS)
    try:
        completed = subprocess.run(
            [sys.executable, str(script), image_path],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(BACKEND_DIR),
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stderr, file=sys.stderr)
            return dict(PLACEHOLDERS)
        stdout = completed.stdout.strip()
        if not stdout:
            return dict(PLACEHOLDERS)
        payload = json.loads(stdout.splitlines()[-1])
        if not isinstance(payload, dict):
            return dict(PLACEHOLDERS)
        return _normalize(payload)
    except Exception as exc:
        print(f"[analyzer] CLI failed: {exc!r}", file=sys.stderr)
        return dict(PLACEHOLDERS)
