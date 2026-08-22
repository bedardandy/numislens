"""Tests for the CSV export/import contract (round-trip, strict validation)."""

from __future__ import annotations

import pytest

from numislens_core.csvio import (
    COIN_CSV_COLUMNS,
    CsvImportError,
    coin_to_csv_row,
    coins_to_csv,
    parse_coins_csv,
)


def _comps():
    return {"90% silver dollar": 4, "steel cent": 3}


def _locs():
    return {"cabinet > box 1": 7, "tray 2": 9}


def test_roundtrip_export_then_parse(ledger):
    accession = ledger.add_coin(
        series="Morgan Dollar",
        year=1885,
        mintmark="CC",
        composition_id=4,
        cost_basis_cents=123456,
        value_est_cents=1000,
        value_basis="hybrid",
        notes='quote " and , comma',
    )
    loc = ledger.create_location("box", "Box 1")
    ledger.edit_coin(accession, location_id=loc)
    ledger.set_disposition(accession, "sold", sold_price_cents=25000, sold_venue="eBay")

    coin = ledger.get_coin(accession)
    row = coin_to_csv_row(
        coin,
        composition_name="90% silver dollar",
        location_path="Cabinet > Box 1",
    )
    text = coins_to_csv([row])

    assert text.splitlines()[0] == ",".join(COIN_CSV_COLUMNS)
    parsed = parse_coins_csv(text, composition_ids_by_name=_comps(), location_ids_by_path=_locs())
    assert len(parsed) == 1
    fields = parsed[0]
    # Identity survives the round-trip; accession/composition/location are
    # translated to portable forms.
    assert fields["series"] == "Morgan Dollar"
    assert fields["year"] == 1885
    assert fields["mintmark"] == "CC"
    assert fields["composition_id"] == 4
    assert fields["cost_basis_cents"] == 123456
    assert fields["sold_price_cents"] == 25000
    assert fields["disposition"] == "sold"
    # Path resolved through the provided map (translation works end-to-end).
    assert fields["location_id"] == _locs()["cabinet > box 1"]
    assert 'quote " and , comma' in fields["notes"]


def test_parse_rejects_unknown_column():
    text = "series,mint\nMorgan,P\n"
    with pytest.raises(CsvImportError) as excinfo:
        parse_coins_csv(text, composition_ids_by_name={}, location_ids_by_path={})
    assert "unknown column" in excinfo.value.errors[0]
    assert "mint" in excinfo.value.errors[0]


def test_parse_collects_every_row_error_and_creates_nothing():
    text = (
        "series,year,cost_basis_cents,composition,location,disposition,sold_price_cents\n"
        "Morgan Dollar,notayear,,,,,\n"
        ",,,,,,,,,\n"
        "Peace Dollar,1921,12.5,,,sold,\n"
        "Peace Dollar,1922,500,Nope comp,,owned,\n"
        "Peace Dollar,1923,500,,Nowhere,sold,\n"
        "Peace Dollar,1924,500,,,sold,\n"
    )
    with pytest.raises(CsvImportError) as excinfo:
        parse_coins_csv(text, composition_ids_by_name=_comps(), location_ids_by_path=_locs())
    joined = "\n".join(excinfo.value.errors)
    assert "row 2: year must be an integer" in joined
    assert "row 3: need at least a series or a year" in joined
    assert "row 4: cost_basis_cents must be non-negative integer cents" in joined
    assert "row 5: unknown composition: 'Nope comp'" in joined
    assert "row 6: unknown location path: 'Nowhere'" in joined
    assert "row 7: disposition='sold' requires sold_price_cents" in joined


def test_parse_accepts_sold_with_zero_price():
    text = (
        "series,year,disposition,sold_price_cents\n"
        "Morgan Dollar,1900,sold,0\n"
    )
    parsed = parse_coins_csv(text, composition_ids_by_name=_comps(), location_ids_by_path=_locs())
    assert parsed[0]["disposition"] == "sold"
    assert parsed[0]["sold_price_cents"] == 0


def test_parse_grade_bucket_case_insensitive():
    text = "series,year,grade_bucket\nMorgan Dollar,1900,vf\n"
    parsed = parse_coins_csv(text, composition_ids_by_name={}, location_ids_by_path={})
    assert parsed[0]["grade_bucket"] == "VF"


def test_parse_empty_or_unrelated_file_is_an_error():
    # A header of known-but-identity-less columns: rows cannot identify a coin.
    with pytest.raises(CsvImportError) as excinfo:
        parse_coins_csv("notes\nhello\n", composition_ids_by_name={}, location_ids_by_path={})
    messages = "\n".join(excinfo.value.errors)
    assert "header has neither" in messages
    assert any("need at least a series or a year" in e for e in excinfo.value.errors)


def test_parse_ignores_accession_no_column():
    text = "accession_no,series,year\nNL-000042,Morgan Dollar,1900\n"
    parsed = parse_coins_csv(text, composition_ids_by_name={}, location_ids_by_path={})
    assert parsed[0]["series"] == "Morgan Dollar"
    assert "accession_no" not in parsed[0]


def test_location_matching_is_case_insensitive():
    text = "series,year,location\nMorgan Dollar,1900,CABINET > BOX 1\n"
    parsed = parse_coins_csv(text, composition_ids_by_name={}, location_ids_by_path=_locs())
    assert parsed[0]["location_id"] == 7
