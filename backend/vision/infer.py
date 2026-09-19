"""MIAS fat segmentation inference via ONNX Runtime (+ overlay export)."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image

from vision.preprocess import (
    CT_SIZE,
    Crop_and_CLAHE,
    Max_Area,
    Read_file,
    Remove_small_components,
    Ruler_calcu,
    Scan_row_col,
    ct_to_nchw,
    mask_to_ct_size,
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = BACKEND_DIR / "models"

INNER_ONNX = Path(os.getenv(
    "MIAS_INNER_ONNX",
    str(DEFAULT_MODELS / "efficientTransUnetB3_inner.onnx"),
))
OUTER_ONNX = Path(os.getenv(
    "MIAS_OUTER_ONNX",
    str(DEFAULT_MODELS / "efficientTransUnetB0_outer.onnx"),
))
IMG_SIZE = int(os.getenv("MIAS_INFER_SIZE", "256"))
THRESH = float(os.getenv("MIAS_MASK_THRESH", "0.5"))

_inner_sess: ort.InferenceSession | None = None
_outer_sess: ort.InferenceSession | None = None
_providers: list[str] = []


def _make_session(path: Path) -> ort.InferenceSession:
    if not path.is_file():
        raise FileNotFoundError(f"Missing ONNX model: {path}")
    avail = set(ort.get_available_providers())
    raw = os.getenv("MIAS_ORT_PROVIDERS", "CPUExecutionProvider").strip()
    prefer = [p.strip() for p in raw.split(",") if p.strip() and p.strip() in avail]
    if not prefer:
        prefer = ["CPUExecutionProvider"]
    return ort.InferenceSession(str(path), providers=prefer)


def ensure_sessions() -> None:
    global _inner_sess, _outer_sess, _providers
    if _inner_sess is not None and _outer_sess is not None:
        return
    _inner_sess = _make_session(INNER_ONNX)
    _outer_sess = _make_session(OUTER_ONNX)
    _providers = _inner_sess.get_providers()


def _preprocess(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    image = Read_file(path)
    ru, ct = Crop_and_CLAHE(image)
    tensor = ct_to_nchw(ct, IMG_SIZE)
    if tensor.shape != (1, 1, IMG_SIZE, IMG_SIZE):
        raise RuntimeError(f"ONNX input must be (1, 1, {IMG_SIZE}, {IMG_SIZE}), got {tensor.shape}")
    return tensor, ru, ct


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _predict_prob(sess: ort.InferenceSession, tensor: np.ndarray) -> np.ndarray:
    input_name = sess.get_inputs()[0].name
    logits = sess.run(None, {input_name: tensor})[0]
    return _sigmoid(logits[0, 0])


def _ruler_metrics(
    outer: np.ndarray,
    inner: np.ndarray,
    ru: np.ndarray,
) -> tuple[float, float, float, float]:
    """Return outerFat, innerFat, length, width. Ruler success → cm² / cm; else 0."""
    scale = Ruler_calcu(ru)
    if not isinstance(scale, tuple):
        logger.warning(
            "Ruler_calcu failed (no bright tick rows); returning 0.0 cm/cm². "
            "Overlay and masks are still produced on the CLAHE CT crop."
        )
        return 0.0, 0.0, 0.0, 0.0
    cm_per_p, area_per_p = scale
    outer_fat = round(float(np.sum(outer != 0) * area_per_p), 2)
    inner_fat = round(float(np.sum(inner != 0) * area_per_p), 2)
    length_px, width_px = Scan_row_col(outer)
    length = round(length_px * cm_per_p, 2)
    width = round(width_px * cm_per_p, 2)
    return outer_fat, inner_fat, length, width


def _colorize_overlay(ct: np.ndarray, inner: np.ndarray, outer: np.ndarray) -> Image.Image:
    """Blend 560×560 masks onto the CLAHE CT crop: outer=amber, inner=cyan."""
    if ct.ndim != 2:
        raise ValueError("CLAHE CT crop must be grayscale")
    if inner.shape != ct.shape:
        inner = mask_to_ct_size(inner.astype(np.float32), 0.5)
    if outer.shape != ct.shape:
        outer = mask_to_ct_size(outer.astype(np.float32), 0.5)
    base = Image.fromarray(ct, mode="L").convert("RGBA")
    inner_m = inner > 0
    outer_m = outer > 0

    overlay = np.array(base, dtype=np.float32)
    # outer amber
    if outer_m.any():
        overlay[outer_m, 0] = overlay[outer_m, 0] * 0.45 + 245 * 0.55
        overlay[outer_m, 1] = overlay[outer_m, 1] * 0.45 + 158 * 0.55
        overlay[outer_m, 2] = overlay[outer_m, 2] * 0.45 + 11 * 0.55
        overlay[outer_m, 3] = 255
    # inner cyan (drawn on top where both exist)
    if inner_m.any():
        overlay[inner_m, 0] = overlay[inner_m, 0] * 0.4 + 34 * 0.6
        overlay[inner_m, 1] = overlay[inner_m, 1] * 0.4 + 211 * 0.6
        overlay[inner_m, 2] = overlay[inner_m, 2] * 0.4 + 238 * 0.6
        overlay[inner_m, 3] = 255
    return Image.fromarray(overlay.astype(np.uint8), mode="RGBA").convert("RGB")


def analyze(path: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
    ensure_sessions()
    assert _inner_sess is not None and _outer_sess is not None
    path = Path(path)
    tensor, ru, ct = _preprocess(path)
    inner_prob = _predict_prob(_inner_sess, tensor)
    outer_prob = _predict_prob(_outer_sess, tensor)
    inner = Remove_small_components(mask_to_ct_size(inner_prob, THRESH), min_area=60)
    outer = Max_Area(mask_to_ct_size(outer_prob, THRESH))
    outer_fat, inner_fat, length, width = _ruler_metrics(outer, inner, ru)

    result: dict[str, Any] = {
        "outerFat": outer_fat,
        "innerFat": inner_fat,
        "length": length,
        "width": width,
        "providers": _providers,
        "inner_onnx": str(INNER_ONNX),
        "outer_onnx": str(OUTER_ONNX),
    }

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = uuid.uuid4().hex
        overlay = _colorize_overlay(ct, inner, outer)
        overlay_path = out / f"{stem}_overlay.jpg"
        overlay.save(overlay_path, quality=92)
        Image.fromarray((inner * 255).astype(np.uint8)).save(out / f"{stem}_inner_mask.png")
        Image.fromarray((outer * 255).astype(np.uint8)).save(out / f"{stem}_outer_mask.png")
        result["overlay_file"] = overlay_path.name
        result["inner_mask_file"] = f"{stem}_inner_mask.png"
        result["outer_mask_file"] = f"{stem}_outer_mask.png"
        if overlay.size != (CT_SIZE, CT_SIZE):
            logger.warning("Overlay size %s != expected %s×%s CLAHE crop", overlay.size, CT_SIZE, CT_SIZE)

    return result
