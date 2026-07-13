"""Tests for the coin-rolls module (bulk holdings + valuation + report rollup)."""

from datetime import datetime, timezone

import pytest

from numislens_core import rolls
from numislens_core.melt import PRIMARY_SOURCE
from numislens_core.report import build_appraisal_report
from numislens_core.rolls import RollError, RollNotFound


def _comp_id(conn, name):
    row = conn.execute(
        "SELECT id FROM compositions WHERE name = ?", (name,)
    ).fetchone()
    assert row is not None, name
    return row["id"]


def _insert_spot(conn, metal, price_cents, *, source=PRIMARY_SOURCE, fetched_at=None):
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at) VALUES (?, ?, ?, ?)",
        (metal, price_cents, source, fetched_at),
    )
    conn.commit()


# --- create / get / list / sequence ----------------------------------------


def test_create_get_and_sequence(ledger):
    r1 = rolls.create_roll(ledger.conn, "cent", 50)
    r2 = rolls.create_roll(ledger.conn, "dime", 50)
    assert r1["roll_no"] == "NR-000001"
    assert r2["roll_no"] == "NR-000002"
    assert r1["status"] == "unopened"
    assert r1["country"] == "US"
    assert r1["count"] == 50

    got = rolls.get_roll(ledger.conn, "NR-000001")
    assert got["roll_no"] == "NR-000001"
    assert got["denomination"] == "cent"

    assert rolls.get_roll(ledger.conn, "NR-999999") is None


def test_list_and_status_filter(ledger):
    rolls.create_roll(ledger.conn, "cent", 50)
    rolls.create_roll(ledger.conn, "dime", 50)
    rolls.update_roll(ledger.conn, "NR-000002", status="searching")

    all_rolls = rolls.list_rolls(ledger.conn)
    assert [r["roll_no"] for r in all_rolls] == ["NR-000001", "NR-000002"]

    searching = rolls.list_rolls(ledger.conn, status="searching")
    assert [r["roll_no"] for r in searching] == ["NR-000002"]
    assert rolls.list_rolls(ledger.conn, status="exhausted") == []


def test_create_resolves_composition_name(ledger):
    r = rolls.create_roll(
        ledger.conn, "dime", 50, composition_name="90% silver dime"
    )
    assert r["composition_id"] == _comp_id(ledger.conn, "90% silver dime")
    assert r["composition_name"] == "90% silver dime"


def test_create_unknown_composition_raises(ledger):
    with pytest.raises(RollError):
        rolls.create_roll(ledger.conn, "dime", 50, composition_name="unobtainium")


def test_create_count_validation(ledger):
    with pytest.raises(RollError):
        rolls.create_roll(ledger.conn, "dime", 0)
    with pytest.raises(RollError):
        rolls.create_roll(ledger.conn, "dime", -3)


# --- update -----------------------------------------------------------------


def test_update_invalid_status_raises(ledger):
    rolls.create_roll(ledger.conn, "dime", 50)
    with pytest.raises(RollError):
        rolls.update_roll(ledger.conn, "NR-000001", status="bogus")


def test_update_unknown_roll_raises(ledger):
    with pytest.raises(RollNotFound):
        rolls.update_roll(ledger.conn, "NR-000001", status="searching")


# --- pull -------------------------------------------------------------------


def test_pull_decrements_and_auto_exhausts(ledger):
    rolls.create_roll(ledger.conn, "dime", 50)
    r = rolls.pull_from_roll(ledger.conn, "NR-000001", 10)
    assert r["count"] == 40
    assert r["status"] == "unopened"

    r = rolls.pull_from_roll(ledger.conn, "NR-000001", 40)
    assert r["count"] == 0
    assert r["status"] == "exhausted"


def test_pull_over_and_bad_count(ledger):
    rolls.create_roll(ledger.conn, "dime", 50)
    with pytest.raises(RollError):
        rolls.pull_from_roll(ledger.conn, "NR-000001", 51)
    with pytest.raises(RollError):
        rolls.pull_from_roll(ledger.conn, "NR-000001", 0)


def test_pull_unknown_roll_raises(ledger):
    with pytest.raises(RollNotFound):
        rolls.pull_from_roll(ledger.conn, "NR-000001", 1)


# --- events (append-only) ---------------------------------------------------


def test_events_logged_with_null_coin_id(ledger):
    rolls.create_roll(ledger.conn, "dime", 50)
    rolls.pull_from_roll(ledger.conn, "NR-000001", 5)
    rows = ledger.conn.execute(
        "SELECT coin_id, event_type, detail FROM events ORDER BY id"
    ).fetchall()
    types = [row["event_type"] for row in rows]
    assert "roll:created" in types
    assert "roll:pulled" in types
    for row in rows:
        assert row["coin_id"] is None
        assert "NR-000001" in row["detail"]


def test_events_are_append_only(ledger):
    rolls.create_roll(ledger.conn, "dime", 50)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        with ledger.conn:
            ledger.conn.execute("UPDATE events SET event_type = 'x'")
    with pytest.raises(sqlite3.IntegrityError):
        with ledger.conn:
            ledger.conn.execute("DELETE FROM events")


# --- valuation --------------------------------------------------------------


def test_face_only_roll(ledger):
    r = rolls.create_roll(ledger.conn, "quarter", 40)
    assert r["face_cents"] == 40 * 25
    assert r["melt_cents"] is None
    assert r["best_cents"] == 1000
    assert r["basis"] == "face"


def test_silver_dime_roll_melt_beats_face(ledger):
    _insert_spot(ledger.conn, "XAG", 6001)
    r = rolls.create_roll(
        ledger.conn, "dime", 50, composition_name="90% silver dime"
    )
    expected_melt = round(50 * 0.07234 * 6001)
    assert r["melt_cents"] == expected_melt
    assert r["face_cents"] == 500
    assert r["best_cents"] == expected_melt
    assert r["basis"] == "melt"


def test_no_spot_leaves_melt_none(ledger):
    r = rolls.create_roll(
        ledger.conn, "dime", 50, composition_name="90% silver dime"
    )
    # No spot row inserted -> melt cannot be computed; face still stands.
    assert r["melt_cents"] is None
    assert r["face_cents"] == 500
    assert r["basis"] == "face"


def test_non_us_denom_is_unvalued(ledger):
    r = rolls.create_roll(ledger.conn, "quarter", 40, country="CA")
    assert r["face_cents"] is None
    assert r["melt_cents"] is None
    assert r["best_cents"] is None
    assert r["basis"] is None


def test_nonstandard_flag(ledger):
    standard = rolls.create_roll(ledger.conn, "dime", 50)
    assert standard["nonstandard"] is False
    short = rolls.create_roll(ledger.conn, "dime", 40)
    assert short["nonstandard"] is True


# --- report integration -----------------------------------------------------


def test_report_roll_totals_and_groups(ledger):
    _insert_spot(ledger.conn, "XAG", 6001)
    # A coin so existing coin-side keys are exercised.
    coin_comp = _comp_id(ledger.conn, "90% silver dollar")
    ledger.add_coin(composition_id=coin_comp, denomination="dollar", value_basis="melt")

    silver = rolls.create_roll(
        ledger.conn, "dime", 50, composition_name="90% silver dime"
    )
    face_roll = rolls.create_roll(ledger.conn, "quarter", 40)
    unvalued = rolls.create_roll(ledger.conn, "quarter", 40, country="CA")

    rep = build_appraisal_report(ledger.conn)
    t = rep["totals"]

    # Existing coin keys unchanged / present.
    assert t["coin_count"] == 1
    assert "best_total_cents" in t

    assert t["roll_count"] == 3
    assert t["roll_face_total_cents"] == 500 + 1000
    assert t["roll_melt_total_cents"] == silver["melt_cents"]
    assert t["roll_best_total_cents"] == silver["best_cents"] + face_roll["best_cents"]
    assert t["grand_total_cents"] == t["best_total_cents"] + t["roll_best_total_cents"]

    group_rolls = rep["groups"]["rolls"]
    assert [g["roll_no"] for g in group_rolls] == [silver["roll_no"], face_roll["roll_no"]]
    assert group_rolls[0]["basis"] == "melt"
    assert group_rolls[0]["value_cents"] == silver["best_cents"]

    assert rep["data_quality"]["rolls_unvalued_count"] == 1
    assert unvalued["roll_no"] not in [g["roll_no"] for g in group_rolls]


def test_report_excludes_exhausted_rolls(ledger):
    rolls.create_roll(ledger.conn, "quarter", 40)
    rolls.pull_from_roll(ledger.conn, "NR-000001", 40)  # -> exhausted, count 0

    rep = build_appraisal_report(ledger.conn)
    assert rep["totals"]["roll_count"] == 0
    assert rep["groups"]["rolls"] == []


def test_report_discloses_roll_metal_missing_spot(ledger):
    # Silver roll but no spot row anywhere -> XAG disclosed as missing spot.
    rolls.create_roll(ledger.conn, "dime", 50, composition_name="90% silver dime")
    rep = build_appraisal_report(ledger.conn)
    assert "XAG" in rep["data_quality"]["metals_missing_spot"]
