"""MIAS fat segmentation inference via ONNX Runtime (+ overlay export)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image

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


def _preprocess(path: Path) -> tuple[np.ndarray, Image.Image]:
    img = Image.open(path).convert("L")
    arr = np.array(img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR), dtype=np.float32) / 255.0
    tensor = arr[None, None, ...]
    return tensor, img


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def _predict_mask(sess: ort.InferenceSession, tensor: np.ndarray) -> np.ndarray:
    input_name = sess.get_inputs()[0].name
    logits = sess.run(None, {input_name: tensor})[0]
    prob = _sigmoid(logits[0, 0])
    return (prob >= THRESH).astype(np.uint8)


def _bbox_metrics(mask: np.ndarray, orig_wh: tuple[int, int]) -> tuple[float, float]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return 0.0, 0.0
    w256 = float(xs.max() - xs.min() + 1)
    h256 = float(ys.max() - ys.min() + 1)
    ow, oh = orig_wh
    length = round(h256 * (oh / float(IMG_SIZE)) / 10.0, 2)
    width = round(w256 * (ow / float(IMG_SIZE)) / 10.0, 2)
    return length, width


def _colorize_overlay(gray: Image.Image, inner: np.ndarray, outer: np.ndarray) -> Image.Image:
    """Resize masks to original size and blend: outer=amber, inner=cyan."""
    base = gray.convert("RGBA")
    ow, oh = base.size
    inner_img = Image.fromarray((inner * 255).astype(np.uint8)).resize((ow, oh), Image.NEAREST)
    outer_img = Image.fromarray((outer * 255).astype(np.uint8)).resize((ow, oh), Image.NEAREST)
    inner_m = np.array(inner_img) > 127
    outer_m = np.array(outer_img) > 127

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
    tensor, gray = _preprocess(path)
    inner = _predict_mask(_inner_sess, tensor)
    outer = _predict_mask(_outer_sess, tensor)
    inner_pct = round(float(inner.mean() * 100.0), 2)
    outer_pct = round(float(outer.mean() * 100.0), 2)
    union = np.clip(inner.astype(np.int16) + outer.astype(np.int16), 0, 1).astype(np.uint8)
    length, width = _bbox_metrics(union, gray.size)

    result: dict[str, Any] = {
        "outerFat": outer_pct,
        "innerFat": inner_pct,
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
        overlay = _colorize_overlay(gray, inner, outer)
        overlay_path = out / f"{stem}_overlay.jpg"
        overlay.save(overlay_path, quality=92)
        # also save binary masks at original resolution for optional download
        ow, oh = gray.size
        Image.fromarray((np.array(Image.fromarray((inner * 255).astype(np.uint8)).resize((ow, oh), Image.NEAREST)))).save(out / f"{stem}_inner_mask.png")
        Image.fromarray((np.array(Image.fromarray((outer * 255).astype(np.uint8)).resize((ow, oh), Image.NEAREST)))).save(out / f"{stem}_outer_mask.png")
        result["overlay_file"] = overlay_path.name
        result["inner_mask_file"] = f"{stem}_inner_mask.png"
        result["outer_mask_file"] = f"{stem}_outer_mask.png"

    return result
