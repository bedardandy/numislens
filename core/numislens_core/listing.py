"""Deterministic listing-kit text and staging CSV for sell prep.

Everything here is assembled ONLY from facts that exist on the record. A
section with no data is omitted entirely — never rendered as a placeholder,
never padded with guesses (AGENTS.md invariant 1). The output is a starting
point for a human seller: it states what the ledger knows, cites provenance,
and stays silent about everything else.

The staging CSV (``listings_csv``) uses eBay bulk-listing COLUMN NAMES where
they are stable and well known (Title, Description, StartPrice, ...). It is a
STAGING format: verify the column mapping against your eBay template version
before upload — this module deliberately emits no invented category or
condition-taxonomy IDs, because guessing those would be fabrication.
"""

from __future__ import annotations

import csv
import io

# Grade bucket -> seller-facing condition phrasing. Photo-grade buckets are
# explicitly labeled as such downstream; this map only expands the acronym.
_GRADE_NAMES = {
    "AG": "About Good",
    "G": "Good",
    "VG": "Very Good",
    "F": "Fine",
    "VF": "Very Fine",
    "XF": "Extremely Fine",
    "AU": "About Uncirculated",
    "UNC": "Uncirculated",
    "PROOF": "Proof",
}

_PHOTO_GRADE_SOURCES = frozenset({"local-vlm", "cross-vote"})

LISTING_CSV_COLUMNS: tuple[str, ...] = (
    "Title",
    "Description",
    "StartPrice",
    "Quantity",
    "Format",
    "Duration",
    "ConditionDescription",
    "CustomLabel",
    "PicCount",
)


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def build_listing_title(coin: dict) -> str:
    """Attribution-only title: year, mintmark, series/denomination.

    Falls back denomination -> 'Coin' so a title ALWAYS exists (marketplaces
    require one), but never invents attributes it does not have.
    """
    accession = coin.get("accession_no") or "coin"
    year = coin.get("year")
    mintmark = coin.get("mintmark")
    series = coin.get("series")
    if not series:
        denomination = coin.get("denomination")
        series = denomination.title() if denomination else f"Coin {accession}"
    prefix = ""
    if year is not None:
        prefix = str(year) + (mintmark or "")
    return f"{prefix} {series}".strip()


def _condition_lines(coin: dict) -> list[str]:
    lines: list[str] = []
    grade = coin.get("grade_bucket")
    source = coin.get("grade_source")
    if grade:
        name = _GRADE_NAMES.get(grade, grade)
        if source in _PHOTO_GRADE_SOURCES:
            lines.append(
                f"Condition: {name} (photo-grade via automated imaging — "
                "an estimate, not a TPG grade)."
            )
        else:
            lines.append(f"Condition: {name}.")
    if coin.get("tpg_cert"):
        lines.append(f"Certified: {coin['tpg_cert']}.")
    return lines


def _value_lines(coin: dict) -> list[str]:
    cents = coin.get("value_est_cents")
    if cents is None:
        return []
    basis = coin.get("value_basis")
    if basis == "melt":
        line = f"Value: {_dollars(cents)} (precious-metal melt — tracks the spot price, recomputed daily)."
    elif basis == "numismatic":
        line = f"Value: {_dollars(cents)} (numismatic estimate)."
    elif basis == "hybrid":
        line = f"Value: {_dollars(cents)} (hybrid: melt floor plus numismatic premium)."
    else:
        line = f"Value: {_dollars(cents)}."
    confidence = coin.get("appraisal_confidence")
    if confidence is not None:
        line += f" Confidence: {confidence}."
    return [line]


def _provenance_lines(appraisals: list[dict] | None, limit: int = 5) -> list[str]:
    if not appraisals:
        return []
    lines: list[str] = []
    for a in appraisals[:limit]:
        parts: list[str] = [str(a.get("appraised_at", ""))[:10]]
        who = a.get("appraised_by")
        if who:
            parts.append(str(who))
        if a.get("grade_bucket"):
            parts.append(f"grade {a['grade_bucket']}")
        if a.get("value_cents") is not None:
            parts.append(_dollars(a["value_cents"]))
        line = "Appraisal " + ", ".join(p for p in parts if p)
        url = a.get("source_url")
        if url:
            line += f" (source: {url})"
        if line:
            lines.append(line + ".")
    return lines


def build_listing_description(coin: dict, appraisals: list[dict] | None = None) -> str:
    """Full listing body from existing facts only; absent sections omitted."""
    sections: list[str] = []

    attribution = build_listing_title(coin)
    country = coin.get("country")
    if country and country != "US":
        attribution += f" ({country})"
    sections.append(attribution)

    sections.extend(_condition_lines(coin))
    sections.extend(_value_lines(coin))

    provenance = _provenance_lines(appraisals)
    if provenance:
        sections.append("Provenance / appraisal trail:")
        sections.extend(f"- {line}" for line in provenance)

    notes = coin.get("notes")
    if notes:
        sections.append(f"Notes: {notes}")

    accession = coin.get("accession_no")
    if accession:
        sections.append(f"Inventory accession {accession} (NumisLens local-first ledger).")

    return "\n\n".join(sections)


def listing_row(coin: dict, *, description: str, image_count: int = 0) -> dict[str, str]:
    """One staging-CSV row. Price falls back to cost basis, then face-value-
    honest absence: an empty StartPrice means the seller must set one."""
    price_cents = coin.get("value_est_cents")
    if price_cents is None:
        price_cents = coin.get("cost_basis_cents")
    grade = coin.get("grade_bucket")
    condition = _GRADE_NAMES.get(grade, grade) if grade else ""
    return {
        "Title": build_listing_title(coin)[:80],  # marketplace title caps
        "Description": description,
        "StartPrice": f"{price_cents / 100:.2f}" if price_cents is not None else "",
        "Quantity": "1",
        "Format": "FixedPrice",
        "Duration": "GTC",
        "ConditionDescription": condition,
        "CustomLabel": coin.get("accession_no") or "",
        "PicCount": str(image_count),
    }


def listings_csv(rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(LISTING_CSV_COLUMNS))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
