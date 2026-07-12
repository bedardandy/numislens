"""Tier passes: T1 OCR (PaddleOCR-VL) and T2 VLM (Qwen), plus optional Gemma.

Each pass returns a plain dataclass of CANONICALIZED readings (or None where a
field could not be resolved). No pass ever emits a guessed value. Prompts are
deliberately narrow and single-purpose (the DiffusionGemma/callcard micro-call
rule): the VLM does FOUR separate small calls rather than one mega-JSON, and the
date call forces a digit-by-digit reading so a hallucinated bare year token is
not trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import canon, endpoints
from .config import VisionConfig
from .endpoints import Image64

# --- Prompts ---------------------------------------------------------------

OCR_PROMPT = (
    "Transcribe every character you can read on these coin images exactly as "
    "printed: all legends, the date digits, and any single mintmark letter. "
    "List the text; do not describe or interpret the coin."
)

VLM_SERIES_PROMPT = (
    "This is a coin. Identify it. Answer in three short lines and nothing else:\n"
    "Series: <the coin series/type name>\n"
    "Denomination: <cent, nickel, dime, quarter, half dollar, or dollar>\n"
    "Country: <issuing country>"
)

VLM_DATE_PROMPT = (
    "Read the date (year) on this coin ONE DIGIT AT A TIME. Look carefully at "
    "each numeral. State each digit separately, left to right, like "
    "'first digit: 1, second digit: 9, ...'. If a digit is unclear, say "
    "'unclear' for that digit. Do not guess the whole year — report the digits."
)

VLM_MINT_PROMPT = (
    "Does this coin have a mintmark? A mintmark is a small letter (one of "
    "P, D, S, O, CC, W). If you see one, answer 'Mintmark: <letter>'. If there "
    "is clearly no mintmark, answer 'Mintmark: none'. If you cannot tell, "
    "answer 'Mintmark: unclear'."
)

VLM_GRADE_PROMPT = (
    "Estimate the CONDITION of this coin from wear only, as ONE bucket from this "
    "ladder (never a number):\n"
    "AG (almost no detail), G (heavy wear, outlines only), VG (some detail), "
    "F (moderate wear, clear detail), VF (light-moderate wear), "
    "XF (light wear, most detail sharp), AU (trace wear on high points), "
    "UNC (no wear).\n"
    "Reply with exactly one of: AG, G, VG, F, VF, XF, AU, UNC."
)


@dataclass
class OCRReading:
    available: bool
    url_used: str | None = None
    text: str = ""
    year: int | None = None
    mintmark_present: bool | None = None
    mintmark_letter: str | None = None
    error: str | None = None


@dataclass
class VLMReading:
    available: bool
    series: str | None = None
    denomination: str | None = None
    country: str | None = None
    year: int | None = None
    mintmark_present: bool | None = None
    mintmark_letter: str | None = None
    grade_bucket: str | None = None
    raw: dict = field(default_factory=dict)
    error: str | None = None


def run_ocr(cfg: VisionConfig, images: list[Image64]) -> OCRReading:
    """T1: read stamped text with the OCR specialist (failover across boxes)."""
    try:
        text, url = endpoints.ocr_with_failover(
            cfg.ocr_urls, cfg.ocr_model, OCR_PROMPT, images, timeout=cfg.ocr_timeout
        )
    except endpoints.AllOCRDown as exc:
        return OCRReading(available=False, error=str(exc))
    present, letter = canon.find_mintmark_in_text(text)
    return OCRReading(
        available=True,
        url_used=url,
        text=text,
        year=canon.find_year_in_text(text),
        mintmark_present=present,
        mintmark_letter=letter,
    )


def _vlm_call(cfg: VisionConfig, prompt: str, images: list[Image64]) -> str:
    return endpoints.chat_vision(
        cfg.vlm_url, cfg.vlm_model, prompt, images, timeout=cfg.vlm_timeout
    )


def _parse_series_call(text: str, known: list[str]) -> tuple[str | None, str | None, str | None]:
    # Ignore keys entirely (Qwen renames them): canonicalize on the raw text
    # PLUS any JSON string values it may have emitted despite the plain-text ask.
    combined = (text or "") + " " + canon.json_string_values(text)
    return (
        canon.canon_series(combined, known),
        canon.canon_denomination(combined),
        canon.canon_country(combined),
    )


def run_vlm(cfg: VisionConfig, images: list[Image64], known_series: list[str]) -> VLMReading:
    """T2: four separate micro-calls; every field canonicalized at the boundary."""
    raw: dict = {}
    try:
        series_txt = _vlm_call(cfg, VLM_SERIES_PROMPT, images)
        raw["series"] = series_txt
        date_txt = _vlm_call(cfg, VLM_DATE_PROMPT, images)
        raw["date"] = date_txt
        mint_txt = _vlm_call(cfg, VLM_MINT_PROMPT, images)
        raw["mintmark"] = mint_txt
        grade_txt = _vlm_call(cfg, VLM_GRADE_PROMPT, images)
        raw["grade"] = grade_txt
    except endpoints.EndpointError as exc:
        return VLMReading(available=False, raw=raw, error=str(exc))

    series, denom, country = _parse_series_call(series_txt, known_series)
    present, letter = canon.canon_mintmark(mint_txt)
    return VLMReading(
        available=True,
        series=series,
        denomination=denom,
        country=country,
        year=canon.parse_year_digits(date_txt),
        mintmark_present=present,
        mintmark_letter=letter,
        grade_bucket=canon.canon_grade(grade_txt),
        raw=raw,
    )


def run_gemma(cfg: VisionConfig, images: list[Image64]) -> VLMReading:
    """Optional T3 voter: year + mintmark only (2 flat micro-calls).

    Returns available=False (never raises) when Gemma is unconfigured or down —
    a missing third voter must never break the pipeline.
    """
    if not cfg.gemma_url:
        return VLMReading(available=False, error="gemma not configured")
    raw: dict = {}
    try:
        date_txt = endpoints.chat_vision(
            cfg.gemma_url, cfg.gemma_model, VLM_DATE_PROMPT, images,
            timeout=cfg.gemma_timeout,
        )
        raw["date"] = date_txt
        mint_txt = endpoints.chat_vision(
            cfg.gemma_url, cfg.gemma_model, VLM_MINT_PROMPT, images,
            timeout=cfg.gemma_timeout,
        )
        raw["mintmark"] = mint_txt
    except endpoints.EndpointError as exc:
        return VLMReading(available=False, raw=raw, error=str(exc))
    present, letter = canon.canon_mintmark(mint_txt)
    return VLMReading(
        available=True,
        year=canon.parse_year_digits(date_txt),
        mintmark_present=present,
        mintmark_letter=letter,
        raw=raw,
    )
