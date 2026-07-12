"""Tests for the Ledger API."""

import json
from pathlib import Path

import pytest

from numislens_core import MoveConflict
from numislens_core.ledger import (
    CoinNotFound,
    Ledger,
    LocationNotFound,
    SlotError,
)
from numislens_core.manifests import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETS_DIR = REPO_ROOT / "core" / "sets"
PEACE_MANIFEST = SETS_DIR / "peace-dollars-1921-1935.json"


def test_accession_sequence_increments(ledger):
    a1 = ledger.add_coin(series="Peace Dollar", year=1921)
    a2 = ledger.add_coin(series="Peace Dollar", year=1922)
    assert a1 == "NL-000001"
    assert a2 == "NL-000002"


def test_accession_zero_padded_six_digits(ledger):
    accession = ledger.add_coin()
    assert accession == "NL-000001"
    assert len(accession) == 9
    assert accession.startswith("NL-")


def test_add_coin_writes_added_event(ledger):
    loc_id = ledger.create_location("cabinet", "Cabinet A")
    accession = ledger.add_coin(series="Morgan", location_id=loc_id)
    coin = ledger.get_coin(accession)
    rows = ledger.conn.execute(
        "SELECT event_type, detail FROM events WHERE coin_id = ?",
        (coin["id"],),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "added"
    assert json.loads(rows[0]["detail"]) == loc_id


def test_events_append_only_blocks_update(ledger):
    ledger.add_coin()
    event_id = ledger.conn.execute("SELECT id FROM events LIMIT 1").fetchone()[0]
    with pytest.raises(Exception, match="append-only"):
        ledger.conn.execute(
            "UPDATE events SET event_type = 'tampered' WHERE id = ?",
            (event_id,),
        )


def test_events_append_only_blocks_delete(ledger):
    ledger.add_coin()
    event_id = ledger.conn.execute("SELECT id FROM events LIMIT 1").fetchone()[0]
    with pytest.raises(Exception, match="append-only"):
        ledger.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def test_appraisals_append_only_blocks_update(ledger):
    accession = ledger.add_coin()
    ledger.record_appraisal(accession, "human")
    appraisal_id = ledger.conn.execute(
        "SELECT id FROM appraisals LIMIT 1"
    ).fetchone()[0]
    with pytest.raises(Exception, match="append-only"):
        ledger.conn.execute(
            "UPDATE appraisals SET appraised_by = 'tampered' WHERE id = ?",
            (appraisal_id,),
        )


def test_appraisals_append_only_blocks_delete(ledger):
    accession = ledger.add_coin()
    ledger.record_appraisal(accession, "human")
    appraisal_id = ledger.conn.execute(
        "SELECT id FROM appraisals LIMIT 1"
    ).fetchone()[0]
    with pytest.raises(Exception, match="append-only"):
        ledger.conn.execute(
            "DELETE FROM appraisals WHERE id = ?", (appraisal_id,)
        )


def test_get_coin_missing_returns_none(ledger):
    assert ledger.get_coin("NL-999999") is None


def test_get_coin_present_returns_dict(ledger):
    accession = ledger.add_coin(series="Peace Dollar", year=1923, mintmark="D")
    coin = ledger.get_coin(accession)
    assert isinstance(coin, dict)
    assert coin["accession_no"] == accession
    assert coin["series"] == "Peace Dollar"
    assert coin["year"] == 1923
    assert coin["mintmark"] == "D"


def test_find_coins_by_series(ledger):
    ledger.add_coin(series="Peace Dollar", year=1921)
    ledger.add_coin(series="Morgan Dollar", year=1881)
    ledger.add_coin(series="Peace Dollar", year=1922)
    results = ledger.find_coins(series="Peace Dollar")
    assert len(results) == 2
    assert all(c["series"] == "Peace Dollar" for c in results)


def test_find_coins_by_year(ledger):
    ledger.add_coin(series="Peace Dollar", year=1921)
    ledger.add_coin(series="Peace Dollar", year=1922)
    results = ledger.find_coins(year=1921)
    assert len(results) == 1
    assert results[0]["year"] == 1921


def test_find_coins_by_location_subtree(ledger):
    cabinet = ledger.create_location("cabinet", "Cabinet A")
    box = ledger.create_location("box", "Box B2", parent=cabinet)
    tray = ledger.create_location("tray", "Tray 3", parent=box)
    slot = ledger.create_location("slot", "Slot 14", parent=tray)
    ledger.add_coin(series="Peace Dollar", location_id=slot)
    ledger.add_coin(series="Morgan Dollar", location_id=cabinet)

    in_subtree = ledger.find_coins(location_id=cabinet)
    assert len(in_subtree) == 2

    in_leaf_only = ledger.find_coins(location_id=slot)
    assert len(in_leaf_only) == 1
    assert in_leaf_only[0]["location_id"] == slot


def test_list_compositions(ledger):
    compositions = ledger.list_compositions()
    assert compositions
    expected_keys = {"id", "name", "metal", "fineness", "precious_weight_ozt"}
    for item in compositions:
        assert set(item.keys()) == expected_keys
    ids = [item["id"] for item in compositions]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    assert any(
        c["name"] == "90% silver dollar" and c["metal"] == "XAG"
        for c in compositions
    )


def test_create_location_and_location_path(ledger):
    cabinet = ledger.create_location("cabinet", "Cabinet A")
    box = ledger.create_location("box", "Box B2", parent=cabinet)
    tray = ledger.create_location("tray", "Tray 3", parent=box)
    slot = ledger.create_location("slot", "Slot 14", parent=tray)
    assert ledger.location_path(slot) == "Cabinet A > Box B2 > Tray 3 > Slot 14"


def test_contents_recursive_vs_non_recursive(ledger):
    cabinet = ledger.create_location("cabinet", "Cabinet A")
    box = ledger.create_location("box", "Box B2", parent=cabinet)
    slot = ledger.create_location("slot", "Slot 1", parent=box)
    ledger.add_coin(series="A", location_id=slot)
    ledger.add_coin(series="B", location_id=cabinet)

    recursive = ledger.contents(cabinet, recursive=True)
    assert len(recursive) == 2

    non_recursive = ledger.contents(cabinet, recursive=False)
    assert len(non_recursive) == 1
    assert non_recursive[0]["series"] == "B"


def test_load_set_manifest_idempotent(ledger):
    manifest = load_manifest(PEACE_MANIFEST)
    expected_slots = len(manifest["slots"])

    set_id_1 = ledger.load_set_manifest(PEACE_MANIFEST)
    count_1 = ledger.conn.execute(
        "SELECT COUNT(*) FROM set_slots WHERE set_id = ?", (set_id_1,)
    ).fetchone()[0]

    set_id_2 = ledger.load_set_manifest(PEACE_MANIFEST)
    count_2 = ledger.conn.execute(
        "SELECT COUNT(*) FROM set_slots WHERE set_id = ?", (set_id_2,)
    ).fetchone()[0]

    assert set_id_1 == set_id_2
    assert count_1 == expected_slots
    assert count_2 == expected_slots


def test_assign_to_slot_and_completion(ledger):
    set_id = ledger.load_set_manifest(PEACE_MANIFEST)
    gaps_before = ledger.set_gaps(set_id)
    filled_before, total = ledger.set_completion(set_id)
    assert filled_before == 0
    assert total == len(gaps_before)

    accession = ledger.add_coin(series="Peace Dollar", year=1921, mintmark="P")
    ledger.assign_to_slot(set_id, {"year": 1921, "mint": "P", "note": "high relief (first year of issue)"}, accession)

    gaps_after = ledger.set_gaps(set_id)
    filled_after, total_after = ledger.set_completion(set_id)
    assert len(gaps_after) == len(gaps_before) - 1
    assert filled_after == 1
    assert total_after == total


def test_set_board(ledger):
    set_id = ledger.load_set_manifest(PEACE_MANIFEST)
    accession = ledger.add_coin(
        series="Peace Dollar", year=1921, mintmark="P", grade_bucket="VF"
    )
    ledger.assign_to_slot(
        set_id,
        {"year": 1921, "mint": "P", "note": "high relief (first year of issue)"},
        accession,
    )

    board = ledger.set_board(set_id)
    assert board["filled"] == 1
    assert board["total"] == board["filled"] + len(ledger.set_gaps(set_id))
    assert len(board["slots"]) == board["total"]

    assigned = next(s for s in board["slots"] if s["year"] == 1921 and s["mint"] == "P")
    assert assigned["accession"] == accession
    assert assigned["grade_bucket"] == "VF"

    for slot in board["slots"]:
        if slot is not assigned:
            assert slot["accession"] is None


def test_assign_to_slot_double_fill_raises_slot_error(ledger):
    set_id = ledger.load_set_manifest(PEACE_MANIFEST)
    slot = {"year": 1922, "mint": "P"}
    a1 = ledger.add_coin(year=1922, mintmark="P")
    a2 = ledger.add_coin(year=1922, mintmark="P")
    ledger.assign_to_slot(set_id, slot, a1)
    with pytest.raises(SlotError, match="already filled"):
        ledger.assign_to_slot(set_id, slot, a2)


def test_assign_to_slot_unknown_slot_raises_slot_error(ledger):
    set_id = ledger.load_set_manifest(PEACE_MANIFEST)
    accession = ledger.add_coin()
    with pytest.raises(SlotError, match="no slot"):
        ledger.assign_to_slot(set_id, {"year": 1900, "mint": "P"}, accession)


def test_add_coin_rejects_bad_grade_bucket(ledger):
    with pytest.raises(ValueError, match="grade_bucket"):
        ledger.add_coin(grade_bucket="MS70")


def test_add_coin_rejects_bad_grade_source(ledger):
    with pytest.raises(ValueError, match="grade_source"):
        ledger.add_coin(grade_source="magic-8-ball")


def test_add_coin_rejects_bad_value_basis(ledger):
    with pytest.raises(ValueError, match="value_basis"):
        ledger.add_coin(value_basis="gut-feel")


def test_record_appraisal_appends_and_latest_returns_newest(ledger):
    accession = ledger.add_coin()
    id1 = ledger.record_appraisal(
        accession,
        "human",
        grade_bucket="VF",
        value_cents=2500,
        value_basis="numismatic",
        appraised_at="2020-01-01T00:00:00+00:00",
    )
    id2 = ledger.record_appraisal(
        accession,
        "cloud",
        grade_bucket="XF",
        value_cents=3500,
        value_basis="hybrid",
        appraised_at="2021-06-15T12:00:00+00:00",
    )
    latest = ledger.latest_appraisal(accession)
    assert latest is not None
    assert latest["id"] == id2
    assert latest["id"] != id1
    assert latest["grade_bucket"] == "XF"
    assert latest["value_cents"] == 3500


def test_record_appraisal_unknown_accession_raises_coin_not_found(ledger):
    with pytest.raises(CoinNotFound):
        ledger.record_appraisal("NL-000099", "human")


def test_record_appraisal_bad_enum_raises(ledger):
    accession = ledger.add_coin()
    with pytest.raises(ValueError, match="grade_bucket"):
        ledger.record_appraisal(accession, "human", grade_bucket="MS65")
    with pytest.raises(ValueError, match="value_basis"):
        ledger.record_appraisal(accession, "human", value_basis="auction")


def test_move_coin_updates_location_and_writes_moved_event(ledger):
    loc_a = ledger.create_location("cabinet", "A")
    loc_b = ledger.create_location("cabinet", "B")
    accession = ledger.add_coin(location_id=loc_a)
    ledger.move_coin(accession, loc_b)

    coin = ledger.get_coin(accession)
    assert coin["location_id"] == loc_b

    coin_id = coin["id"]
    row = ledger.conn.execute(
        "SELECT event_type, detail FROM events WHERE coin_id = ? AND event_type = 'moved'",
        (coin_id,),
    ).fetchone()
    assert row is not None
    detail = json.loads(row["detail"])
    assert detail == {"from": loc_a, "to": loc_b}


def test_move_coin_unknown_accession_raises_coin_not_found(ledger):
    loc = ledger.create_location("cabinet", "A")
    with pytest.raises(CoinNotFound):
        ledger.move_coin("NL-000099", loc)


def test_move_coin_unknown_location_raises_location_not_found(ledger):
    accession = ledger.add_coin()
    with pytest.raises(LocationNotFound):
        ledger.move_coin(accession, 9999)


def test_move_coin_conflict_raises(ledger):
    loc_a = ledger.create_location("cabinet", "A")
    loc_b = ledger.create_location("cabinet", "B")
    accession = ledger.add_coin(location_id=loc_a)
    coin_id = ledger.get_coin(accession)["id"]

    with pytest.raises(MoveConflict) as exc_info:
        ledger.move_coin(accession, loc_b, expected_from=loc_b)

    assert exc_info.value.accession == accession
    assert exc_info.value.expected_from == loc_b
    assert exc_info.value.actual == loc_a
    assert ledger.get_coin(accession)["location_id"] == loc_a

    row = ledger.conn.execute(
        "SELECT event_type FROM events WHERE coin_id = ? AND event_type = 'moved'",
        (coin_id,),
    ).fetchone()
    assert row is None


def test_move_coin_with_matching_expected_from_succeeds(ledger):
    loc_a = ledger.create_location("cabinet", "A")
    loc_b = ledger.create_location("cabinet", "B")
    accession = ledger.add_coin(location_id=loc_a)
    ledger.move_coin(accession, loc_b, expected_from=loc_a)
    assert ledger.get_coin(accession)["location_id"] == loc_b


def test_move_coin_without_expected_from_unchanged(ledger):
    loc_a = ledger.create_location("cabinet", "A")
    loc_b = ledger.create_location("cabinet", "B")
    accession = ledger.add_coin(location_id=loc_a)
    ledger.move_coin(accession, loc_b)
    assert ledger.get_coin(accession)["location_id"] == loc_b


# --- Phase 4: vision writeback (fill-null identification) -------------------


def test_update_identification_fills_null_only(ledger):
    acc = ledger.add_coin(year=1943)  # series null, mintmark null
    result = ledger.update_identification(
        acc, series="Lincoln Wheat Cent", year=1949, mintmark="D"
    )
    # series+mintmark were null -> written; year already set -> skipped (never
    # overwrite a value the coin already had).
    assert result["written"] == {"series": "Lincoln Wheat Cent", "mintmark": "D"}
    assert result["skipped"] == {"year": 1943}
    coin = ledger.get_coin(acc)
    assert coin["series"] == "Lincoln Wheat Cent"
    assert coin["mintmark"] == "D"
    assert coin["year"] == 1943  # unchanged


def test_update_identification_sets_grade_with_source(ledger):
    acc = ledger.add_coin(series="Peace Dollar", year=1921)
    result = ledger.update_identification(
        acc, grade_bucket="XF", grade_source="local-vlm"
    )
    assert result["written"] == {"grade_bucket": "XF", "grade_source": "local-vlm"}
    coin = ledger.get_coin(acc)
    assert coin["grade_bucket"] == "XF"
    assert coin["grade_source"] == "local-vlm"


def test_update_identification_appends_identified_event(ledger):
    acc = ledger.add_coin(year=1943)
    ledger.update_identification(acc, series="Lincoln Wheat Cent")
    coin_id = ledger._coin_id(acc)
    rows = ledger.conn.execute(
        "SELECT event_type, detail FROM events WHERE coin_id = ? AND event_type = 'identified'",
        (coin_id,),
    ).fetchall()
    assert len(rows) == 1
    assert "Lincoln Wheat Cent" in rows[0]["detail"]


def test_update_identification_no_writes_appends_no_event(ledger):
    acc = ledger.add_coin(series="Peace Dollar", year=1921, mintmark="P")
    result = ledger.update_identification(acc, series="Morgan Dollar")
    assert result["written"] == {}
    assert result["skipped"] == {"series": "Peace Dollar"}
    coin_id = ledger._coin_id(acc)
    n = ledger.conn.execute(
        "SELECT COUNT(*) FROM events WHERE coin_id = ? AND event_type = 'identified'",
        (coin_id,),
    ).fetchone()[0]
    assert n == 0


def test_update_identification_invalid_grade_source_raises(ledger):
    acc = ledger.add_coin(year=1943)
    with pytest.raises(ValueError, match="grade_source"):
        ledger.update_identification(acc, grade_bucket="XF", grade_source="bogus")


def test_update_identification_unknown_field_raises(ledger):
    acc = ledger.add_coin(year=1943)
    with pytest.raises(ValueError, match="identification fields"):
        ledger.update_identification(acc, value_est_cents=100)


def test_update_identification_unknown_coin_raises(ledger):
    with pytest.raises(CoinNotFound):
        ledger.update_identification("NL-999999", series="x")


def test_list_appraisals_newest_first(ledger):
    acc = ledger.add_coin(year=1943)
    ledger.record_appraisal(acc, "human", grade_bucket="VF", appraised_at="2026-01-01T00:00:00+00:00")
    ledger.record_appraisal(acc, "vision:cross-vote", grade_bucket="XF", appraised_at="2026-02-01T00:00:00+00:00")
    rows = ledger.list_appraisals(acc)
    assert len(rows) == 2
    assert rows[0]["appraised_by"] == "vision:cross-vote"  # newest first
    assert rows[1]["appraised_by"] == "human"
