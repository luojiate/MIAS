# syntax=docker/dockerfile:1
# MIAS all-in-one image: Vite SPA + FastAPI + CPU ONNX Runtime.
# Local GPU workflow stays on uv (`onnxruntime-gpu` in pyproject.toml).

# --- frontend: Node 24 + pnpm (matches fnm / packageManager) ---
FROM node:24-bookworm-slim AS frontend
WORKDIR /src/frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable && corepack prepare pnpm@12.4.2 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Same-origin API when FastAPI serves this build (104 resume = one Render URL).
ENV VITE_BACKEND_URL=
RUN VITE_BACKEND_URL= pnpm run build

# --- backend: Python 3.12 + CPU onnxruntime ---
FROM python:3.12-slim-bookworm AS backend
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      libgomp1 \
      libglib2.0-0 \
      libgl1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin mias

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Locked deps from uv export; replace GPU wheel with CPU onnxruntime for Render/Linux.
COPY backend/requirements.txt /tmp/requirements.txt
RUN sed -i 's/^onnxruntime-gpu==/onnxruntime==/' /tmp/requirements.txt \
 && uv pip install --system --no-cache -r /tmp/requirements.txt \
 && rm -f /tmp/requirements.txt

COPY --chown=mias:mias backend/ /app/
COPY --from=frontend --chown=mias:mias /src/frontend/dist /app/frontend/dist

RUN mkdir -p /app/uploads \
 && chown mias:mias /app/uploads

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MIAS_ORT_PROVIDERS=CPUExecutionProvider \
    UPLOAD_DIR=/app/uploads \
    SPA_DIR=/app/frontend/dist

USER mias
EXPOSE 8000
# Render injects PORT (often 10000). No --reload in production.
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
