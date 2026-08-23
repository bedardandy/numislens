"""Tests for the deterministic listing-kit builder (no-fabrication rules)."""

from __future__ import annotations

import csv
import io

import pytest

from numislens_core.listing import (
    LISTING_CSV_COLUMNS,
    build_listing_description,
    build_listing_title,
    listing_row,
    listings_csv,
)


def test_title_uses_only_present_attribution():
    coin = {"accession_no": "NL-000001", "year": 1931, "mintmark": "S",
            "series": "Lincoln Wheat Cent"}
    assert build_listing_title(coin) == "1931S Lincoln Wheat Cent"

    no_mint = dict(coin, mintmark=None)
    assert build_listing_title(no_mint) == "1931 Lincoln Wheat Cent"

    denom_only = {"accession_no": "NL-000002", "denomination": "half dollar"}
    assert build_listing_title(denom_only) == "Half Dollar"

    bare = {"accession_no": "NL-000003"}
    assert build_listing_title(bare) == "Coin NL-000003"


def test_description_omits_absent_sections_never_placeholders():
    bare = {"accession_no": "NL-000004", "year": 1952, "series": "Lincoln Wheat Cent"}
    text = build_listing_description(bare)
    assert text.startswith("1952 Lincoln Wheat Cent")
    assert "Condition:" not in text
    assert "Value:" not in text
    assert "Notes:" not in text
    assert "None" not in text and "null" not in text
    assert "Inventory accession NL-000004" in text


def test_description_condition_labels_photo_grade_honestly():
    photo = {"accession_no": "NL-000005", "year": 1900, "series": "X",
             "grade_bucket": "VF", "grade_source": "local-vlm"}
    assert "photo-grade" in build_listing_description(photo)
    assert "not a TPG grade" in build_listing_description(photo)

    human = dict(photo, grade_source="human")
    assert "photo-grade" not in build_listing_description(human)
    assert "Condition: Very Fine." in build_listing_description(human)


def test_description_value_lines_by_basis():
    melt = {"accession_no": "NL-6", "value_est_cents": 4641, "value_basis": "melt"}
    assert "melt" in build_listing_description(melt)
    assert "$46.41" in build_listing_description(melt)

    hybrid = dict(melt, value_basis="hybrid", appraisal_confidence=0.8)
    text = build_listing_description(hybrid)
    assert "hybrid" in text and "Confidence: 0.8" in text

    unspecified = dict(melt, value_basis=None)
    assert "Value: $46.41." in build_listing_description(unspecified)


def test_description_provenance_includes_citations():
    coin = {"accession_no": "NL-000007", "year": 1932, "series": "Washington Quarter"}
    appraisals = [
        {
            "appraised_at": "2026-08-01T12:00:00+00:00",
            "appraised_by": "human",
            "grade_bucket": "G",
            "value_cents": 12500,
            "source_url": "https://auctions.example/lot/42",
        },
        {
            "appraised_at": "2026-07-01T12:00:00+00:00",
            "appraised_by": "vision:local-vlm",
            "grade_bucket": "G",
            "value_cents": None,
            "source_url": None,
        },
    ]
    text = build_listing_description(coin, appraisals)
    assert "Provenance / appraisal trail:" in text
    assert "https://auctions.example/lot/42" in text
    assert "Appraisal 2026-08-01, human, grade G, $125.00" in text
    # Newest first, capped at 5.
    assert text.index("2026-08-01") < text.index("2026-07-01")


def test_listing_row_price_fallback_and_title_cap():
    coin = {"accession_no": "NL-000008", "year": 1900, "series": "S" * 100,
            "value_est_cents": 500}
    row = listing_row(coin, description="body", image_count=2)
    assert row["Title"].endswith("…") is False
    assert len(row["Title"]) <= 80
    assert row["StartPrice"] == "5.00"
    assert row["Quantity"] == "1"
    assert row["CustomLabel"] == "NL-000008"
    assert row["PicCount"] == "2"

    no_price = {"accession_no": "NL-9", "cost_basis_cents": 25}
    assert listing_row(no_price, description="b")["StartPrice"] == "0.25"
    assert listing_row({"accession_no": "NL-10"}, description="b")["StartPrice"] == ""


def test_listings_csv_roundtrip_shape():
    rows = [
        listing_row({"accession_no": "NL-1", "year": 1900, "series": "S"},
                    description="a\nb", image_count=1),
    ]
    text = listings_csv(rows)
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == list(LISTING_CSV_COLUMNS)
    parsed = list(reader)
    assert parsed[0]["CustomLabel"] == "NL-1"
    assert parsed[0]["Description"] == "a\nb"
