"""Guards for the production Docker / Render hosting files."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestDockerfile(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def test_exists(self) -> None:
        self.assertTrue((ROOT / "Dockerfile").is_file())
        self.assertTrue((ROOT / ".dockerignore").is_file())
        self.assertTrue((ROOT / "render.yaml").is_file())

    def test_cpu_onnxruntime_override(self) -> None:
        self.assertIn("s/^onnxruntime-gpu==/onnxruntime==/", self.text)
        self.assertIn("CPUExecutionProvider", self.text)
        self.assertIn("pnpm", self.text)
        self.assertIn("node:24", self.text)

    def test_uvicorn_binds_port_without_reload(self) -> None:
        self.assertIn("0.0.0.0", self.text)
        self.assertIn("${PORT:-8000}", self.text)
        cmd = self.text.split("CMD", 1)[-1]
        self.assertNotIn("--reload", cmd)

    def test_spa_copied_into_image(self) -> None:
        self.assertIn("frontend/dist", self.text)
        self.assertIn("VITE_BACKEND_URL=", self.text)


class TestRenderYaml(unittest.TestCase):
    def test_web_docker_env(self) -> None:
        text = (ROOT / "render.yaml").read_text(encoding="utf-8")
        for needle in (
            "type: web",
            "runtime: docker",
            "healthCheckPath: /health",
            "MONGO_URI",
            "SESSION_SECRET",
            "PUBLIC_URL",
            "CORS_ORIGINS",
            "MIAS_ORT_PROVIDERS",
            "CPUExecutionProvider",
        ):
            self.assertIn(needle, text)


class TestDockerignoreKeepsModels(unittest.TestCase):
    def test_does_not_exclude_onnx(self) -> None:
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.split("#", 1)[0].strip()
            if not stripped:
                continue
            self.assertFalse(stripped.endswith(".onnx"), line)
            self.assertNotIn(stripped, {"backend/models", "backend/models/", "**/models", "models"})


if __name__ == "__main__":
    unittest.main()
