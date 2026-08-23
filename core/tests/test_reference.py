"""Tests for the curated value-reference loader and lookup semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from numislens_core.reference import (
    REFERENCE_DIR,
    ReferenceError,
    ReferenceSet,
    load_references,
    validate_reference,
)


@pytest.fixture(scope="module")
def shipped() -> ReferenceSet:
    return load_references()


def test_shipped_datasets_load_and_validate(shipped):
    assert len(shipped) == 3
    ids = {d["id"] for d in shipped.datasets}
    assert ids == {"lincoln-wheat-cents", "washington-quarters-1932-1964", "jefferson-nickels"}
    # Provenance is mandatory and complete for every dataset.
    for source in shipped.sources():
        assert source["source"]["url"].startswith("https://")
        assert len(source["source"]["retrieved"]) == 10


def test_lookup_requires_exact_identity_and_grade(shipped):
    # Exact hit.
    assert shipped.lookup("Lincoln Wheat Cent", 1914, "D", "G") == 30000
    # Series matching is case-insensitive.
    assert shipped.lookup("lincoln wheat cent", 1914, "D", "G") == 30000
    # Wrong grade: no interpolation to a nearby bucket, ever.
    assert shipped.lookup("Lincoln Wheat Cent", 1914, "D", "VG") is None
    assert shipped.lookup("Lincoln Wheat Cent", 1914, "D", None) is None
    # Wrong year / mintmark / series: nothing.
    assert shipped.lookup("Lincoln Wheat Cent", 1913, "D", "G") is None
    assert shipped.lookup("Lincoln Wheat Cent", 1914, None, "G") is None
    assert shipped.lookup("Morgan Dollar", 1914, "D", "G") is None


def test_wildcard_mintmark_entry_matches_any_mintmark_but_not_none(shipped):
    # The common-ladder entry (mintmark null) matches any specific mintmark...
    assert shipped.lookup("Lincoln Wheat Cent", 1955, None, None) is None  # flag-only
    # ...but there are no graded wildcard rows in the shipped data; verify the
    # wildcard rule directly with a synthetic set below (test_synthetic).


def test_grade_null_entries_never_return_values(shipped):
    # 1932-D has an any-condition flag entry at 1500 — it must not surface
    # as a value for an ungraded coin or any other grade miss.
    assert shipped.lookup("Washington Quarter", 1932, "D", None) is None
    assert shipped.lookup("Washington Quarter", 1932, "D", "AG") is None


def test_conservative_min_across_datasets():
    refs = ReferenceSet(
        [
            {
                "schema_version": 1,
                "id": "a",
                "name": "A",
                "series": "Test Series",
                "source": {"name": "s", "url": "https://x.example", "retrieved": "2026-01-01"},
                "entries": [{"year": 2000, "mintmark": None, "grade": "F", "value_cents": 500}],
            },
            {
                "schema_version": 1,
                "id": "b",
                "name": "B",
                "series": "test series",
                "source": {"name": "s", "url": "https://x.example", "retrieved": "2026-01-01"},
                "entries": [{"year": 2000, "mintmark": None, "grade": "F", "value_cents": 900}],
            },
        ]
    )
    # Two datasets agree on the identity but disagree on price: conservative wins.
    assert refs.lookup("Test Series", 2000, None, "F") == 500
    # Flagging wants attention: max wins there.
    assert refs.notable_value("TEST SERIES", 2000, None) == 900


def test_synthetic_wildcard_and_threshold_semantics(tmp_path: Path):
    d = tmp_path
    (d / "wild.json").write_text(
        """
        {
          "schema_version": 1, "id": "wild", "name": "Wild",
          "series": "Wildcard Series", "notable_threshold_cents": 10000,
          "source": {"name": "s", "url": "https://x.example", "retrieved": "2026-01-01"},
          "entries": [
            {"year": 1990, "mintmark": null, "grade": "VF", "value_cents": 250},
            {"year": 1990, "mintmark": null, "grade": "UNC", "value_cents": 12000},
            {"year": 1991, "mintmark": "D", "grade": "VF", "value_cents": 400},
            {"year": 1991, "mintmark": "S", "grade": null, "value_cents": 15000}
          ]
        }
        """,
        encoding="utf-8",
    )
    refs = load_references(d)
    # Wildcard graded entry matches every mintmark including none.
    assert refs.lookup("Wildcard Series", 1990, None, "VF") == 250
    assert refs.lookup("Wildcard Series", 1990, "P", "VF") == 250
    # A lettered entry does NOT match a coin with no mintmark.
    assert refs.lookup("Wildcard Series", 1991, None, "VF") is None
    assert refs.lookup("Wildcard Series", 1991, "D", "VF") == 400
    # Threshold: only >=10000 entries count as notable.
    assert refs.notable_value("Wildcard Series", 1990, "P") == 12000
    assert refs.notable_value("Wildcard Series", 1991, "S") == 15000
    assert refs.notable_value("Wildcard Series", 1991, "D") is None  # 400 < threshold


def test_validation_rejects_unknown_keys_and_bad_values():
    base = {
        "schema_version": 1,
        "id": "x",
        "name": "X",
        "series": "X Series",
        "source": {"name": "s", "url": "https://x.example", "retrieved": "2026-01-01"},
        "entries": [{"year": 2000, "value_cents": 5}],
    }

    bad_top = dict(base, oops=True)
    with pytest.raises(ReferenceError, match="unknown top-level key"):
        validate_reference(bad_top)

    with pytest.raises(ReferenceError, match="schema_version"):
        validate_reference(dict(base, schema_version=2))

    bad_url = dict(base)
    bad_url["source"] = {"name": "s", "url": "ftp://nope", "retrieved": "2026-01-01"}
    with pytest.raises(ReferenceError, match="http"):
        validate_reference(bad_url)

    bad_date = dict(base)
    bad_date["source"] = {"name": "s", "url": "https://x", "retrieved": "Aug 1 2026"}
    with pytest.raises(ReferenceError, match="YYYY-MM-DD"):
        validate_reference(bad_date)

    bad_country = dict(base, country="CA")
    with pytest.raises(ReferenceError, match="country"):
        validate_reference(bad_country)

    zero = dict(base, entries=[{"year": 2000, "value_cents": 0}])
    with pytest.raises(ReferenceError, match="positive integer"):
        validate_reference(zero)

    bad_mint = dict(base, entries=[{"year": 2000, "mintmark": "Q", "value_cents": 5}])
    with pytest.raises(ReferenceError, match="mintmark"):
        validate_reference(bad_mint)

    bad_grade = dict(base, entries=[{"year": 2000, "grade": "MS70", "value_cents": 5}])
    with pytest.raises(ReferenceError, match="grade"):
        validate_reference(bad_grade)

    dup = dict(
        base,
        entries=[
            {"year": 2000, "grade": "F", "value_cents": 5},
            {"year": 2000, "grade": "F", "value_cents": 6},
        ],
    )
    with pytest.raises(ReferenceError, match="duplicate identity"):
        validate_reference(dup)


def test_validation_rejects_descending_ladder():
    data = {
        "schema_version": 1,
        "id": "desc",
        "name": "Descending",
        "series": "Desc Series",
        "source": {"name": "s", "url": "https://x.example", "retrieved": "2026-01-01"},
        "entries": [
            {"year": 2000, "grade": "F", "value_cents": 500},
            {"year": 2000, "grade": "VF", "value_cents": 400},
        ],
    }
    with pytest.raises(ReferenceError, match="must not descend"):
        validate_reference(data)


def test_shipped_directory_is_the_default():
    assert REFERENCE_DIR.name == "reference"
    assert (REFERENCE_DIR / "reference.schema.json").is_file()
