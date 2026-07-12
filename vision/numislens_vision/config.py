"""Environment-driven configuration for the vision pipeline.

Every endpoint is configurable so the pipeline is portable across the LAN GPU
fleet. Defaults point at the boxes surveyed live on 2026-07-12:

- OCR (PaddleOCR-VL-1.6): both Strix boxes, tried in order with failover.
- VLM (Qwen3.6-27B-FP8 vision): p920.
- Gemma (optional third voter): NO default — it must be opted in explicitly.
  The pipeline runs and reports its absence when unset or unreachable; a down
  Gemma is never fatal.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Live-surveyed defaults (2026-07-12). Override via env for other deployments.
DEFAULT_DAEMON_URL = "http://127.0.0.1:8471"
DEFAULT_OCR_URLS = "http://beyondmax:8080,http://framedesk:8080"
DEFAULT_VLM_URL = "http://p920-server:8088"
DEFAULT_OCR_MODEL = "PaddlePaddle/PaddleOCR-VL-1.6-GGUF:GGUF"
DEFAULT_VLM_MODEL = "Qwen3.6-27B-FP8"
DEFAULT_GEMMA_MODEL = "gemma-4-12b"


@dataclass(frozen=True)
class VisionConfig:
    # Daemon (the ledger REST API — source of images + writeback target).
    daemon_url: str
    token: str
    # OCR specialist (identity-critical TEXT: date digits, mintmark, legend).
    ocr_urls: tuple[str, ...]
    ocr_model: str
    # VLM cross-vote (series/date/mintmark/condition).
    vlm_url: str
    vlm_model: str
    # Optional third voter. gemma_url is None when unconfigured.
    gemma_url: str | None
    gemma_model: str
    # HTTP timeouts (seconds). VLM calls can be slow on first load.
    ocr_timeout: float = 120.0
    vlm_timeout: float = 180.0
    gemma_timeout: float = 60.0
    # Downscale longest image edge to this many px before base64 (0 = no resize).
    max_image_edge: int = 1024


def _split_urls(raw: str) -> tuple[str, ...]:
    return tuple(u.strip().rstrip("/") for u in raw.split(",") if u.strip())


def load_config(require_token: bool = True) -> VisionConfig:
    daemon_url = os.environ.get("NUMISLENS_URL", DEFAULT_DAEMON_URL).rstrip("/")
    token = os.environ.get("NUMISLENS_TOKEN", "").strip()
    if require_token and not token:
        raise RuntimeError(
            "NUMISLENS_TOKEN is not set. Export the daemon bearer token, e.g. "
            "export NUMISLENS_TOKEN=... (the same token the daemon uses)."
        )

    ocr_urls = _split_urls(os.environ.get("VISION_OCR_URLS", DEFAULT_OCR_URLS))
    if not ocr_urls:
        raise RuntimeError(
            "VISION_OCR_URLS resolved to an empty list; set at least one "
            "OpenAI-compatible OCR endpoint (comma-separated for failover)."
        )

    gemma_url_raw = os.environ.get("VISION_GEMMA_URL", "").strip().rstrip("/")
    gemma_url = gemma_url_raw or None

    return VisionConfig(
        daemon_url=daemon_url,
        token=token,
        ocr_urls=ocr_urls,
        ocr_model=os.environ.get("VISION_OCR_MODEL", DEFAULT_OCR_MODEL),
        vlm_url=os.environ.get("VISION_VLM_URL", DEFAULT_VLM_URL).rstrip("/"),
        vlm_model=os.environ.get("VISION_VLM_MODEL", DEFAULT_VLM_MODEL),
        gemma_url=gemma_url,
        gemma_model=os.environ.get("VISION_GEMMA_MODEL", DEFAULT_GEMMA_MODEL),
    )
