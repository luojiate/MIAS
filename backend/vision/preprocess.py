"""Old MIAS web Crop_and_CLAHE / ruler / mask cleanup (OpenCV).

Clinical inputs should be full-size scanner exports like the original app
(large enough for a 560×560 center crop plus a left-hand 12 px ruler strip).
Already-processed 560×560 images yield a full-frame crop (center ±280) and
CLAHE once. Smaller images are zero-padded so the crop stays 560×560.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2 as cv
import numpy as np

logger = logging.getLogger(__name__)

CT_HALF = 280
CT_SIZE = CT_HALF * 2  # 560
RULER_WIDTH = 12
CLAHE_CLIP = 2.0
CLAHE_TILE = (8, 8)
INNER_MIN_AREA = 60
MORPH_KERNEL = (3, 3)


def Read_file(file_path: str | Path) -> np.ndarray:
    path = str(file_path)
    image = cv.imread(path, cv.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("無法讀取影像: {}".format(path))
    return image


def _pad_for_crop(image: np.ndarray, ct_ax: int, ct_ay: int, ct_bx: int, ct_by: int) -> tuple[np.ndarray, int, int]:
    """Zero-pad so the ruler strip and 560×560 center crop stay in-bounds."""
    h, w = image.shape[:2]
    pad_top = max(0, -ct_ay)
    pad_left = max(0, -min(ct_ax, 0))
    pad_bottom = max(0, ct_by - h)
    pad_right = max(0, max(ct_bx, RULER_WIDTH) - w)
    if not (pad_top or pad_left or pad_bottom or pad_right):
        return image, 0, 0
    logger.warning(
        "Image %sx%s is smaller than the clinical 560×560 center-crop; "
        "padding with zeros. Full-size scanner exports are expected.",
        h,
        w,
    )
    padded = cv.copyMakeBorder(
        image,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        cv.BORDER_CONSTANT,
        value=0,
    )
    return padded, pad_left, pad_top


def Crop_and_CLAHE(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = image.shape[:2]
    ru_ax, ru_ay = 0, 0
    ru_bx, ru_by = RULER_WIDTH, h
    ct_ax, ct_ay = int(w / 2) - CT_HALF, int(h / 2) - CT_HALF
    ct_bx, ct_by = int(w / 2) + CT_HALF, int(h / 2) + CT_HALF

    image, dx, dy = _pad_for_crop(image, ct_ax, ct_ay, ct_bx, ct_by)
    ru_ax += dx
    ru_bx += dx
    ru_ay += dy
    ru_by += dy
    ct_ax += dx
    ct_bx += dx
    ct_ay += dy
    ct_by += dy

    ru = image[ru_ay:ru_by, ru_ax:ru_bx]
    ct = image[ct_ay:ct_by, ct_ax:ct_bx]
    if ct.shape != (CT_SIZE, CT_SIZE):
        # Safety net if padding/slice math is off; clinical path should not hit this.
        ct = cv.resize(ct, (CT_SIZE, CT_SIZE), interpolation=cv.INTER_LINEAR)
    ct = cv.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE).apply(ct)
    return ru, ct


def Ruler_calcu(ru: np.ndarray) -> int | tuple[float, float]:
    if ru.size == 0 or ru.ndim != 2:
        return 0
    brightness_of_each_row = np.sum(ru, axis=1)
    rows_with_high_brightness = np.where(brightness_of_each_row > 1800)[0]
    if rows_with_high_brightness.size == 0:
        return 0
    min_1800_index = int(rows_with_high_brightness[0])
    max_1800_index = int(rows_with_high_brightness[-1])
    count_of_5cm = int(rows_with_high_brightness.size)
    span = max_1800_index - min_1800_index + 1
    if span <= 0:
        return 0
    cm_per_p = (count_of_5cm - 1) * 5 / span
    if cm_per_p <= 0:
        return 0
    area_per_p = cm_per_p ** 2
    return cm_per_p, area_per_p


def Max_Area(img: np.ndarray) -> np.ndarray:
    """Keep the largest connected component, then MORPH_CLOSE 3×3."""
    binary = np.ascontiguousarray((img > 0).astype(np.uint8))
    num_labels, labels, stats, _centroids = cv.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return binary
    largest_label = 1 + int(np.argmax(stats[1:, cv.CC_STAT_AREA]))
    kept = np.zeros(labels.shape, dtype=np.uint8)
    kept[labels == largest_label] = 1
    kernel = np.ones(MORPH_KERNEL, np.uint8)
    closed = cv.morphologyEx(kept, cv.MORPH_CLOSE, kernel)
    return (closed > 0).astype(np.uint8)


def Remove_small_components(img: np.ndarray, min_area: int = INNER_MIN_AREA) -> np.ndarray:
    binary = np.ascontiguousarray((img > 0).astype(np.uint8))
    num_labels, labels, stats, _centroids = cv.connectedComponentsWithStats(binary, connectivity=8)
    kept = np.zeros(labels.shape, dtype=np.uint8)
    for i in range(1, num_labels):
        if stats[i, cv.CC_STAT_AREA] >= min_area:
            kept[labels == i] = 1
    return kept


def Scan_row_col(pred: np.ndarray) -> tuple[int, int]:
    """Bounding-box height/width in pixels of the non-zero region."""
    ys, xs = np.where(pred > 0)
    if ys.size == 0:
        return 0, 0
    length = int(ys.max() - ys.min() + 1)
    width = int(xs.max() - xs.min() + 1)
    return length, width


def mask_to_ct_size(mask_or_prob: np.ndarray, thresh: float) -> np.ndarray:
    """Resize a 256 map to 560×560 (old `cv.resize(..., (560,560))`) then threshold."""
    resized = cv.resize(
        mask_or_prob.astype(np.float32),
        (CT_SIZE, CT_SIZE),
        interpolation=cv.INTER_LINEAR,
    )
    return (resized >= thresh).astype(np.uint8)


def ct_to_nchw(ct: np.ndarray, img_size: int) -> np.ndarray:
    """Keras-style HWC /255 then transpose to NCHW `(1, 1, img_size, img_size)`."""
    ct_resize = cv.resize(ct, (img_size, img_size), interpolation=cv.INTER_LINEAR)
    hwc = np.expand_dims(ct_resize.astype(np.float32), axis=-1) / 255.0
    nhwc = np.expand_dims(hwc, axis=0)
    return np.transpose(nhwc, (0, 3, 1, 2))
