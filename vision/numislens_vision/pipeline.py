"""Orchestrate the tiered identification pipeline for one coin.

Pure REST client: fetches the coin's stored obverse/reverse images from the
daemon, runs the tier passes against the LAN GPU endpoints, applies the
deterministic gate, and returns a data-only result. NO writes here — writeback
is a separate, opt-in step (see writeback.py / worker.py). NO core import, NO DB.
"""

from __future__ import annotations

from typing import Any

from . import tiers
from .config import VisionConfig
from .daemon_client import DaemonClient
from .endpoints import Image64
from .gate import run_gate


def _select_images(cfg: VisionConfig, client: DaemonClient, coin: dict) -> tuple[list[Image64], list[str]]:
    """Fetch obverse+reverse image bytes, downscale, and prep for embedding.

    Returns (images, notes). ``notes`` records which sides were missing so the
    result is honest about what the tiers actually saw.
    """
    accession = coin["accession_no"]
    by_kind = {img["kind"]: img["content_hash"] for img in coin.get("coin_images", [])}
    images: list[Image64] = []
    notes: list[str] = []
    for kind in ("obverse", "reverse"):
        h = by_kind.get(kind)
        if h is None:
            notes.append(f"no {kind} image")
            continue
        raw = client.get_image_bytes(accession, h)
        images.append(Image64.from_bytes(raw, max_edge=cfg.max_image_edge))
    return images, notes


def identify(cfg: VisionConfig, accession: str, client: DaemonClient | None = None) -> dict:
    """Run the pipeline for one coin and return the gated result (no writes)."""
    client = client or DaemonClient(cfg)
    coin = client.get_coin(accession)

    images, image_notes = _select_images(cfg, client, coin)

    tiers_used: list[str] = []
    tiers_unavailable: list[str] = []

    if not images:
        # Nothing to look at — fail loud, write nothing, everything unresolved.
        return {
            "accession": accession,
            "accepted": {
                "series": None, "year": None, "mintmark": None,
                "grade_bucket": None, "grade_confidence": None,
            },
            "escalations": [
                {
                    "field": "images",
                    "readings": {"coin_images": coin.get("coin_images", [])},
                    "note": "no obverse/reverse image on the coin; " + ", ".join(image_notes),
                }
            ],
            "tiers_used": [],
            "tiers_unavailable": ["ocr: no images", "vlm: no images", "gemma: no images"],
        }

    known_series = client.known_series()
    key_date_years = client.key_date_years()

    ocr = tiers.run_ocr(cfg, images)
    if ocr.available:
        tiers_used.append(f"ocr:{ocr.url_used}")
    else:
        tiers_unavailable.append(f"ocr: {ocr.error}")

    vlm = tiers.run_vlm(cfg, images, known_series)
    if vlm.available:
        tiers_used.append(f"vlm:{cfg.vlm_url}")
    else:
        tiers_unavailable.append(f"vlm: {vlm.error}")

    gemma = tiers.run_gemma(cfg, images)
    if gemma.available:
        tiers_used.append(f"gemma:{cfg.gemma_url}")
    else:
        tiers_unavailable.append(f"gemma: {gemma.error}")

    gated = run_gate(ocr, vlm, gemma, key_date_years=key_date_years)

    result: dict[str, Any] = {
        "accession": accession,
        "accepted": gated["accepted"],
        "escalations": gated["escalations"],
        "tiers_used": tiers_used,
        "tiers_unavailable": tiers_unavailable,
    }
    if image_notes:
        result["image_notes"] = image_notes
    return result
