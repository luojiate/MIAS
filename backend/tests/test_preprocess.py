"""Unit tests for the old-MIAS Crop_and_CLAHE / ruler / mask pipeline."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2 as cv
import numpy as np
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


def _gray(h: int, w: int, value: int = 80) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


class TestReadFile(unittest.TestCase):
    def test_missing_path_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            Read_file("/tmp/this-file-does-not-exist-mias.png")
        self.assertIn("無法讀取影像", str(ctx.exception))

    def test_non_image_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"not an image")
            path = tmp.name
        try:
            with self.assertRaises(ValueError):
                Read_file(path)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_roundtrip_png(self) -> None:
        img = _gray(64, 80, 40)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        cv.imwrite(path, img)
        try:
            got = Read_file(path)
            self.assertEqual(got.shape, (64, 80))
            self.assertEqual(got.dtype, np.uint8)
        finally:
            Path(path).unlink(missing_ok=True)


class TestCropAndClahe(unittest.TestCase):
    def test_already_560_is_full_frame(self) -> None:
        # Non-flat so CLAHE actually changes pixels.
        yy, xx = np.mgrid[0:CT_SIZE, 0:CT_SIZE]
        image = ((xx + yy) % 256).astype(np.uint8)
        ru, ct = Crop_and_CLAHE(image)
        self.assertEqual(ct.shape, (CT_SIZE, CT_SIZE))
        self.assertEqual(ru.shape[1], 12)
        self.assertEqual(ru.shape[0], CT_SIZE)
        self.assertFalse(np.array_equal(ct, image), "CLAHE should run once on the full 560 frame")

    def test_small_image_pads_to_560(self) -> None:
        image = _gray(200, 180, 90)
        _ru, ct = Crop_and_CLAHE(image)
        self.assertEqual(ct.shape, (CT_SIZE, CT_SIZE))

    def test_large_image_center_crop(self) -> None:
        h, w = 900, 800
        image = np.zeros((h, w), dtype=np.uint8)
        cy, cx = int(h / 2), int(w / 2)
        image[cy - CT_SIZE // 2 : cy + CT_SIZE // 2, cx - CT_SIZE // 2 : cx + CT_SIZE // 2] = 200
        _ru, ct = Crop_and_CLAHE(image)
        self.assertEqual(ct.shape, (CT_SIZE, CT_SIZE))
        # Center of the crop came from the bright 560 block (CLAHE keeps it bright).
        self.assertGreater(int(ct[CT_SIZE // 2, CT_SIZE // 2]), 100)


class TestRulerAndMetrics(unittest.TestCase):
    def test_ruler_success(self) -> None:
        ru = np.zeros((200, 12), dtype=np.uint8)
        ticks = [20, 40, 60, 80, 100]  # 5 ticks, 5 cm apart in the old convention
        for y in ticks:
            ru[y, :] = 255
        scale = Ruler_calcu(ru)
        self.assertIsInstance(scale, tuple)
        cm_per_p, area_per_p = scale
        span = ticks[-1] - ticks[0] + 1
        expected = (len(ticks) - 1) * 5 / span
        self.assertAlmostEqual(cm_per_p, expected)
        self.assertAlmostEqual(area_per_p, expected ** 2)

    def test_ruler_failure_returns_zero(self) -> None:
        self.assertEqual(Ruler_calcu(np.zeros((100, 12), dtype=np.uint8)), 0)
        self.assertEqual(Ruler_calcu(np.zeros((0, 12), dtype=np.uint8)), 0)

    def test_scan_row_col(self) -> None:
        mask = np.zeros((20, 30), dtype=np.uint8)
        mask[5:12, 3:10] = 1  # 7 rows × 7 cols
        self.assertEqual(Scan_row_col(mask), (7, 7))
        self.assertEqual(Scan_row_col(np.zeros((10, 10), dtype=np.uint8)), (0, 0))


class TestMaskCleanup(unittest.TestCase):
    def test_max_area_keeps_largest(self) -> None:
        mask = np.zeros((80, 80), dtype=np.uint8)
        mask[2:6, 2:6] = 1  # small 16 px
        mask[20:50, 20:50] = 1  # large 900 px
        kept = Max_Area(mask)
        self.assertEqual(kept.dtype, np.uint8)
        self.assertGreater(int(kept[30, 30]), 0)
        self.assertEqual(int(kept[3, 3]), 0)

    def test_remove_small_components(self) -> None:
        mask = np.zeros((80, 80), dtype=np.uint8)
        mask[2:6, 2:6] = 1  # 16 px < 60
        mask[20:30, 20:30] = 1  # 100 px
        kept = Remove_small_components(mask, min_area=60)
        self.assertEqual(int(kept[3, 3]), 0)
        self.assertEqual(int(kept[25, 25]), 1)

    def test_resize_threshold_to_560(self) -> None:
        prob = np.zeros((256, 256), dtype=np.float32)
        prob[64:192, 64:192] = 0.9
        binary = mask_to_ct_size(prob, 0.5)
        self.assertEqual(binary.shape, (CT_SIZE, CT_SIZE))
        self.assertIn(int(binary.max()), (0, 1))
        self.assertGreater(int(binary.sum()), 0)


class TestModelInput(unittest.TestCase):
    def test_nchw_shape_and_range(self) -> None:
        ct = _gray(CT_SIZE, CT_SIZE, 128)
        tensor = ct_to_nchw(ct, 256)
        self.assertEqual(tensor.shape, (1, 1, 256, 256))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(np.all(tensor >= 0.0) and np.all(tensor <= 1.0))
        self.assertAlmostEqual(float(tensor.mean()), 128 / 255.0, places=4)


class TestInferHelpers(unittest.TestCase):
    def test_preprocess_tensor_and_ct(self) -> None:
        from vision.infer import _preprocess

        yy, xx = np.mgrid[0:CT_SIZE, 0:CT_SIZE]
        image = ((xx // 2) % 256).astype(np.uint8)
        # Left strip bright enough to look like a ruler (optional).
        image[:, :12] = 10
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        cv.imwrite(path, image)
        try:
            tensor, ru, ct = _preprocess(Path(path))
            self.assertEqual(tensor.shape, (1, 1, 256, 256))
            self.assertEqual(ct.shape, (CT_SIZE, CT_SIZE))
            self.assertEqual(ru.shape[1], 12)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_overlay_is_560_rgb(self) -> None:
        from vision.infer import _colorize_overlay

        ct = _gray(CT_SIZE, CT_SIZE, 60)
        inner = np.zeros((CT_SIZE, CT_SIZE), dtype=np.uint8)
        outer = np.zeros((CT_SIZE, CT_SIZE), dtype=np.uint8)
        inner[200:260, 200:260] = 1
        outer[160:300, 160:300] = 1
        overlay = _colorize_overlay(ct, inner, outer)
        self.assertEqual(overlay.size, (CT_SIZE, CT_SIZE))
        self.assertEqual(overlay.mode, "RGB")

    def test_ruler_metrics_zero_without_ticks(self) -> None:
        from vision.infer import _ruler_metrics

        outer = np.ones((CT_SIZE, CT_SIZE), dtype=np.uint8)
        inner = np.ones((CT_SIZE, CT_SIZE), dtype=np.uint8)
        ru = np.zeros((CT_SIZE, 12), dtype=np.uint8)
        self.assertEqual(_ruler_metrics(outer, inner, ru), (0.0, 0.0, 0.0, 0.0))

    def test_ruler_metrics_area_and_span(self) -> None:
        from vision.infer import _ruler_metrics

        ru = np.zeros((200, 12), dtype=np.uint8)
        ticks = [20, 40, 60, 80, 100]
        for y in ticks:
            ru[y, :] = 255
        cm_per_p, area_per_p = Ruler_calcu(ru)
        outer = np.zeros((40, 40), dtype=np.uint8)
        outer[10:20, 5:15] = 1  # 100 px, bbox 10×10
        inner = np.zeros((40, 40), dtype=np.uint8)
        inner[12:16, 8:12] = 1  # 16 px
        of, inf, length, width = _ruler_metrics(outer, inner, ru)
        self.assertAlmostEqual(of, round(100 * area_per_p, 2))
        self.assertAlmostEqual(inf, round(16 * area_per_p, 2))
        self.assertAlmostEqual(length, round(10 * cm_per_p, 2))
        self.assertAlmostEqual(width, round(10 * cm_per_p, 2))


class TestAnalyzeIntegration(unittest.TestCase):
    def test_analyze_writes_560_overlay(self) -> None:
        from vision.infer import INNER_ONNX, OUTER_ONNX, analyze

        if not INNER_ONNX.is_file() or not OUTER_ONNX.is_file():
            self.skipTest("ONNX weights not present")
        image = np.zeros((720, 640), dtype=np.uint8)
        yy, xx = np.ogrid[:720, :640]
        image[...] = np.clip((xx + yy) // 5, 0, 255).astype(np.uint8)
        # Synthetic ruler ticks on the left strip (full-height clinical layout).
        for y in range(40, 680, 40):
            image[y : y + 2, 0:12] = 255
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "scan.png"
            cv.imwrite(str(src), image)
            result = analyze(src, out_dir=td)
            self.assertEqual(set(result) & {"outerFat", "innerFat", "length", "width"}, {"outerFat", "innerFat", "length", "width"})
            with Image.open(Path(td) / result["overlay_file"]) as overlay:
                self.assertEqual(overlay.size, (CT_SIZE, CT_SIZE))
            with Image.open(Path(td) / result["inner_mask_file"]) as inner_m:
                self.assertEqual(inner_m.size, (CT_SIZE, CT_SIZE))
            with Image.open(Path(td) / result["outer_mask_file"]) as outer_m:
                self.assertEqual(outer_m.size, (CT_SIZE, CT_SIZE))


if __name__ == "__main__":
    unittest.main()
