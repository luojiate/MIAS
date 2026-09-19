"""API tests for POST /upload-images (mocked inference, no Mongo)."""
from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app import MAX_BATCH_FILES, app

FAKE_METRICS = {
    "outerFat": 1.25,
    "innerFat": 0.5,
    "length": 3.0,
    "width": 2.0,
    "overlay_file": None,
    "inner_mask_file": None,
    "outer_mask_file": None,
}


def _png_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buf, format="PNG")
    return buf.getvalue()


class TestUploadImages(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.client = TestClient(app, raise_server_exceptions=True, lifespan="off")
        except TypeError:
            self.client = TestClient(app, raise_server_exceptions=True)

    def test_empty_files_returns_400(self) -> None:
        with patch("app.require_userid", return_value="user-1"):
            response = self.client.post("/upload-images")
        self.assertEqual(response.status_code, 400)
        self.assertIn("請至少選擇一張影像", response.json()["detail"])

    def test_too_many_files_returns_400(self) -> None:
        payload = _png_bytes()
        files = [
            ("images", (f"scan-{i}.png", payload, "image/png"))
            for i in range(MAX_BATCH_FILES + 1)
        ]
        with (
            patch("app.require_userid", return_value="user-1"),
            patch("app.analyze_image") as analyze,
        ):
            response = self.client.post("/upload-images", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertIn("一次最多上傳", response.json()["detail"])
        self.assertIn(str(MAX_BATCH_FILES), response.json()["detail"])
        analyze.assert_not_called()

    def test_happy_path_two_images(self) -> None:
        files = [
            ("images", ("alpha.png", _png_bytes((40, 50, 60)), "image/png")),
            ("images", ("beta.png", _png_bytes((70, 80, 90)), "image/png")),
        ]
        with (
            patch("app.require_userid", return_value="user-1"),
            patch("app.analyze_image", return_value=dict(FAKE_METRICS)) as analyze,
        ):
            response = self.client.post("/upload-images", files=files)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["succeeded"], 2)
        self.assertEqual(body["failed"], 0)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(analyze.call_count, 2)
        names = [item["filename"] for item in body["results"]]
        self.assertEqual(names, ["alpha.png", "beta.png"])
        for item in body["results"]:
            self.assertTrue(item["success"])
            self.assertIn("/uploads/", item["image"])
            self.assertEqual(item["outerFat"], 1.25)
            self.assertEqual(item["innerFat"], 0.5)
            self.assertEqual(item["length"], 3.0)
            self.assertEqual(item["width"], 2.0)

        for call in analyze.call_args_list:
            saved = Path(call.args[0])
            self.assertTrue(saved.is_file())
            saved.unlink(missing_ok=True)

    def test_unauthenticated_returns_401(self) -> None:
        files = [("images", ("alpha.png", _png_bytes(), "image/png"))]
        response = self.client.post("/upload-images", files=files)
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
