"""The deterministic agreement gate.

This is the descendant of the P0 fabrication bug: NOTHING here ever emits a
guessed value. A field is ACCEPTED only when the tiers agree under the rules
below; otherwise it goes to ESCALATION with every tier's raw reading shown, for
a Tier-3 human/assistant to adjudicate. The gate does no I/O and no model calls
— pure functions over the tier readings.

Rules (as shipped)
------------------
year, mintmark (mintmark token: a letter, "NONE" = affirmatively no mark, or
absent = unreadable):
  * Two-tier mode (no Gemma / Gemma down): accept iff BOTH OCR and VLM produced
    the SAME reading (for mintmark, "both saw none" == agreement). Any
    disagreement, or either tier unreadable -> escalate.
  * Three-tier mode (Gemma up): 2-of-3 agreement wins (a strict majority value
    with >= 2 votes and no rival also at 2).
  * KEY-DATE OVERRIDE (value-relevant): if ANY tier read a year that is a
    key-date year in a loaded set manifest, BOTH year and mintmark require
    UNANIMITY across ALL available tiers (every available tier read it and all
    agree). This is the ~100x-value 1914 vs 1914-D case; conservatively keyed at
    the year level (more escalation, never less).
series:
  * Accepted from the VLM alone IF it canonicalized to a known series; else
    escalate. (OCR/Gemma do not vote on series.)
grade_bucket:
  * From the VLM alone, always flagged low-confidence ("photo-grade"); never a
    cross-vote, never an MS-numeric. Unreadable -> escalate.
"""

from __future__ import annotations

from typing import Any

from .tiers import OCRReading, VLMReading


def _mint_token(reading: OCRReading | VLMReading | None) -> str | None:
    """Normalize a tier's mintmark reading to a comparable token.

    Returns a letter, the sentinel "NONE" (affirmatively saw no mintmark), or
    None (tier unavailable or could not tell).
    """
    if reading is None or not reading.available:
        return None
    if reading.mintmark_present is True and reading.mintmark_letter:
        return reading.mintmark_letter
    if reading.mintmark_present is False:
        return "NONE"
    return None


def _vote(readings: dict[str, Any], *, three_tier: bool) -> tuple[Any, bool]:
    """Return (accepted_value, ok). ``readings`` maps tier -> value (or None).

    ok=False means escalate. Two-tier: OCR and VLM must both be present and
    equal. Three-tier: a value with a strict >=2 majority wins.
    """
    present = {t: v for t, v in readings.items() if v is not None}
    if three_tier:
        counts: dict[Any, int] = {}
        for v in present.values():
            counts[v] = counts.get(v, 0) + 1
        winners = [v for v, c in counts.items() if c >= 2]
        if len(winners) == 1:
            return winners[0], True
        return None, False
    # Two-tier: strict unanimity of OCR and VLM.
    ocr_v = readings.get("ocr")
    vlm_v = readings.get("vlm")
    if ocr_v is not None and vlm_v is not None and ocr_v == vlm_v:
        return ocr_v, True
    return None, False


def _all_available_agree(readings: dict[str, Any], available: set[str]) -> tuple[Any, bool]:
    """Unanimity among ALL available tiers (each read it, all equal)."""
    vals = []
    for tier in available:
        v = readings.get(tier)
        if v is None:
            return None, False
        vals.append(v)
    if not vals:
        return None, False
    if all(v == vals[0] for v in vals):
        return vals[0], True
    return None, False


def run_gate(
    ocr: OCRReading,
    vlm: VLMReading,
    gemma: VLMReading,
    *,
    key_date_years: set[int],
) -> dict:
    """Apply the gate; return {accepted, escalations}."""
    three_tier = gemma.available
    available: set[str] = set()
    if ocr.available:
        available.add("ocr")
    if vlm.available:
        available.add("vlm")
    if gemma.available:
        available.add("gemma")

    year_readings: dict[str, Any] = {"ocr": ocr.year, "vlm": vlm.year}
    mint_readings: dict[str, Any] = {"ocr": _mint_token(ocr), "vlm": _mint_token(vlm)}
    if gemma.available:
        year_readings["gemma"] = gemma.year
        mint_readings["gemma"] = _mint_token(gemma)

    # Key-date relevance: conservative, year-level, across ANY tier's reading.
    candidate_years = {y for y in year_readings.values() if isinstance(y, int)}
    key_relevant = bool(candidate_years & key_date_years)

    accepted: dict[str, Any] = {
        "series": None,
        "year": None,
        "mintmark": None,
        "grade_bucket": None,
        "grade_confidence": None,
    }
    escalations: list[dict] = []

    def esc(field: str, readings: dict[str, Any], note: str) -> None:
        escalations.append({"field": field, "readings": dict(readings), "note": note})

    # --- year + mintmark ---------------------------------------------------
    if key_relevant:
        # Unanimity among available tiers is only a check when there is more
        # than one independent reader. With OCR or the VLM down, "everyone
        # available agrees" would degenerate to a single unverified reading —
        # on exactly the coins where a wrong digit or mint letter costs most.
        if {"ocr", "vlm"} <= available:
            y_val, y_ok = _all_available_agree(year_readings, available)
            m_val, m_ok = _all_available_agree(mint_readings, available)
            note = "key-date year: all available tiers must agree"
        else:
            y_val, y_ok = None, False
            m_val, m_ok = None, False
            note = "key-date year: needs both OCR and VLM available to cross-check"
        if y_ok:
            accepted["year"] = y_val
        else:
            esc("year", year_readings, note)
        if m_ok:
            accepted["mintmark"] = None if m_val == "NONE" else m_val
        else:
            esc("mintmark", mint_readings, note)
    else:
        y_val, y_ok = _vote(year_readings, three_tier=three_tier)
        m_val, m_ok = _vote(mint_readings, three_tier=three_tier)
        if y_ok:
            accepted["year"] = y_val
        else:
            esc("year", year_readings, "OCR/VLM year readings do not agree")
        if m_ok:
            accepted["mintmark"] = None if m_val == "NONE" else m_val
        else:
            esc("mintmark", mint_readings, "mintmark readings do not agree")

    # --- series (VLM only) -------------------------------------------------
    series_readings = {"vlm": vlm.series, "vlm_raw": (vlm.raw or {}).get("series")}
    if vlm.available and vlm.series:
        accepted["series"] = vlm.series
    else:
        note = "VLM unavailable" if not vlm.available else "series did not canonicalize"
        esc("series", series_readings, note)

    # --- grade bucket (VLM only, photo-grade) ------------------------------
    grade_readings = {"vlm": vlm.grade_bucket, "vlm_raw": (vlm.raw or {}).get("grade")}
    if vlm.available and vlm.grade_bucket:
        accepted["grade_bucket"] = vlm.grade_bucket
        accepted["grade_confidence"] = "photo-grade"
    else:
        note = "VLM unavailable" if not vlm.available else "grade did not canonicalize"
        esc("grade_bucket", grade_readings, note)

    return {"accepted": accepted, "escalations": escalations}
