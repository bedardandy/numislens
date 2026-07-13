"""Tests for the appraisal-report module (per-coin valuation + rollups)."""

from datetime import datetime, timezone

import pytest

from numislens_core.melt import PRIMARY_SOURCE
from numislens_core.report import build_appraisal_report, face_value_cents

# Silver dollar: 0.77344 ozt at 6001c/ozt spot.
SILVER_DOLLAR_MELT = round(0.77344 * 6001)  # 4641


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
        """
        INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at)
        VALUES (?, ?, ?, ?)
        """,
        (metal, price_cents, source, fetched_at),
    )
    conn.commit()


# --- face_value_cents unit coverage -----------------------------------------


def test_face_value_cents_us_denominations():
    assert face_value_cents("quarter", "US") == 25
    assert face_value_cents("  Half Dollar  ", "US") == 50
    assert face_value_cents("DOLLAR", "US") == 100
    assert face_value_cents("cent", "US") == 1


def test_face_value_cents_non_us_is_none():
    assert face_value_cents("quarter", "CA") is None
    assert face_value_cents("quarter", None) is None


def test_face_value_cents_unknown_denomination_is_none():
    assert face_value_cents("crown", "US") is None
    assert face_value_cents(None, "US") is None


# --- per-coin valuation and buckets -----------------------------------------


def test_silver_coin_melt_wins(ledger):
    # 1. silver coin, spot present, no collectible estimate -> melt beats face.
    comp = _comp_id(ledger.conn, "90% silver dollar")
    _insert_spot(ledger.conn, "XAG", 6001)
    acc = ledger.add_coin(composition_id=comp, denomination="dollar")

    rep = build_appraisal_report(ledger.conn)

    assert rep["breakdown"]["melt"] == {"count": 1, "total_cents": SILVER_DOLLAR_MELT}
    assert rep["breakdown"]["collectible"]["count"] == 0
    (h,) = rep["highlights"]
    assert h["accession_no"] == acc
    assert h["best_basis"] == "melt"
    assert h["best_cents"] == SILVER_DOLLAR_MELT
    assert h["melt_cents"] == SILVER_DOLLAR_MELT
    assert h["face_cents"] == 100
    assert h["collectible_cents"] is None


def test_numismatic_collectible_wins(ledger):
    # 2. numismatic estimate dominates.
    comp = _comp_id(ledger.conn, "90% silver dollar")
    _insert_spot(ledger.conn, "XAG", 6001)
    ledger.add_coin(
        composition_id=comp,
        denomination="dollar",
        value_basis="numismatic",
        value_est_cents=500000,
    )

    rep = build_appraisal_report(ledger.conn)

    assert rep["breakdown"]["collectible"] == {"count": 1, "total_cents": 500000}
    assert rep["breakdown"]["melt"]["count"] == 0
    assert rep["totals"]["best_total_cents"] == 500000
    # component totals still record melt and face where present
    assert rep["totals"]["melt_total_cents"] == SILVER_DOLLAR_MELT
    assert rep["totals"]["face_total_cents"] == 100


def test_clad_quarter_face_bucket(ledger):
    # 3. clad coin, no composition value and no estimate -> face (quarter = 25).
    comp = _comp_id(ledger.conn, "Cupronickel clad")
    ledger.add_coin(composition_id=comp, denomination="quarter")

    rep = build_appraisal_report(ledger.conn)

    assert rep["breakdown"]["face"] == {"count": 1, "total_cents": 25}
    (h,) = rep["highlights"]
    assert h["best_basis"] == "face"
    assert h["best_cents"] == 25
    assert h["melt_cents"] is None
    assert h["collectible_cents"] is None


def test_fully_unknown_coin_is_unvalued(ledger):
    # 4. no denom / composition / estimate -> unvalued, disclosed, excluded.
    ledger.add_coin()

    rep = build_appraisal_report(ledger.conn)

    assert rep["totals"]["coin_count"] == 1
    assert rep["totals"]["valued_count"] == 0
    assert rep["totals"]["unvalued_count"] == 1
    assert rep["totals"]["best_total_cents"] == 0
    assert rep["breakdown"]["unvalued"] == {"count": 1}
    assert rep["data_quality"]["unvalued_count"] == 1
    assert rep["data_quality"]["no_composition_count"] == 1
    assert rep["highlights"] == []


def test_collectible_melt_tie_collectible_wins(ledger):
    # 5. equal collectible and melt -> collectible wins on priority.
    comp = _comp_id(ledger.conn, "90% silver dollar")
    _insert_spot(ledger.conn, "XAG", 6001)
    ledger.add_coin(
        composition_id=comp,
        denomination="dollar",
        value_basis="numismatic",
        value_est_cents=SILVER_DOLLAR_MELT,
    )

    rep = build_appraisal_report(ledger.conn)

    assert rep["breakdown"]["collectible"]["count"] == 1
    assert rep["breakdown"]["melt"]["count"] == 0
    (h,) = rep["highlights"]
    assert h["best_basis"] == "collectible"
    assert h["best_cents"] == SILVER_DOLLAR_MELT


def test_highlights_ordering_and_top_n_truncation(ledger):
    # 6. top_n ordering (best desc, accession asc) + truncation.
    comp = _comp_id(ledger.conn, "Cupronickel clad")
    # Two dollars (100) then a dime (10); dollars tie -> accession ascending.
    a1 = ledger.add_coin(composition_id=comp, denomination="dollar")
    a2 = ledger.add_coin(composition_id=comp, denomination="dollar")
    ledger.add_coin(composition_id=comp, denomination="dime")

    rep = build_appraisal_report(ledger.conn, top_n=2)

    assert rep["top_n"] == 2
    assert [h["accession_no"] for h in rep["highlights"]] == [a1, a2]
    assert all(h["best_cents"] == 100 for h in rep["highlights"])
    assert a1 < a2  # tie broken by accession ascending


def test_missing_spot_melt_none_and_disclosed(ledger):
    # 7. silver coin, no spot -> melt None, metal in metals_missing_spot.
    comp = _comp_id(ledger.conn, "90% silver dollar")
    ledger.add_coin(composition_id=comp, denomination="dollar")

    rep = build_appraisal_report(ledger.conn)

    assert rep["data_quality"]["metals_missing_spot"] == ["XAG"]
    assert rep["spot"] == {}
    (h,) = rep["highlights"]
    assert h["melt_cents"] is None
    assert h["best_basis"] == "face"  # falls back to face


def test_non_us_country_face_none(ledger):
    # 8. non-US country -> face None; with nothing else it is unvalued.
    ledger.add_coin(denomination="quarter", country="CA")

    rep = build_appraisal_report(ledger.conn)

    assert rep["totals"]["face_total_cents"] == 0
    assert rep["totals"]["unvalued_count"] == 1


def test_null_basis_with_estimate_counts_unspecified(ledger):
    # 9. value_basis NULL but estimate present -> collectible + flagged.
    ledger.add_coin(value_est_cents=7500)

    rep = build_appraisal_report(ledger.conn)

    assert rep["data_quality"]["basis_unspecified_count"] == 1
    assert rep["breakdown"]["collectible"] == {"count": 1, "total_cents": 7500}


def test_melt_basis_coin_not_double_counted(ledger):
    # 10. value_basis='melt' with a mirrored estimate -> melt bucket, no
    # collectible (the estimate is NOT re-counted as a premium).
    comp = _comp_id(ledger.conn, "90% silver dollar")
    _insert_spot(ledger.conn, "XAG", 6001)
    ledger.add_coin(
        composition_id=comp,
        denomination="dollar",
        value_basis="melt",
        value_est_cents=SILVER_DOLLAR_MELT,
    )

    rep = build_appraisal_report(ledger.conn)

    assert rep["breakdown"]["melt"] == {"count": 1, "total_cents": SILVER_DOLLAR_MELT}
    assert rep["totals"]["collectible_total_cents"] == 0
    (h,) = rep["highlights"]
    assert h["collectible_cents"] is None
    assert h["best_basis"] == "melt"
    assert rep["data_quality"]["basis_unspecified_count"] == 0


def test_sets_group_partial_fill(ledger):
    # 11. a set with slots partially filled: filled/total/value correct.
    comp = _comp_id(ledger.conn, "Cupronickel clad")
    acc = ledger.add_coin(composition_id=comp, denomination="quarter")
    coin_id = ledger.conn.execute(
        "SELECT id FROM coins WHERE accession_no = ?", (acc,)
    ).fetchone()["id"]

    ledger.conn.execute(
        "INSERT INTO sets (set_key, name) VALUES ('washington', 'Washington Quarters')"
    )
    set_id = ledger.conn.execute(
        "SELECT id FROM sets WHERE set_key = 'washington'"
    ).fetchone()["id"]
    ledger.conn.execute(
        "INSERT INTO set_slots (set_id, year, mint, coin_id) VALUES (?, 1932, 'P', ?)",
        (set_id, coin_id),
    )
    ledger.conn.execute(
        "INSERT INTO set_slots (set_id, year, mint) VALUES (?, 1932, 'D')",
        (set_id,),
    )
    ledger.conn.commit()

    rep = build_appraisal_report(ledger.conn)

    (s,) = rep["groups"]["sets"]
    assert s["set_key"] == "washington"
    assert s["total_slots"] == 2
    assert s["filled"] == 1
    assert s["owned_count"] == 1
    assert s["value_cents"] == 25  # face of the one filled quarter


def test_mints_series_metals_group_sums(ledger):
    # 12. group sums for mints / series / metals.
    silver = _comp_id(ledger.conn, "90% silver dollar")
    clad = _comp_id(ledger.conn, "Cupronickel clad")
    _insert_spot(ledger.conn, "XAG", 6001)

    ledger.add_coin(
        composition_id=silver, denomination="dollar", series="Morgan", mintmark="S"
    )
    ledger.add_coin(
        composition_id=clad, denomination="quarter", series="Washington", mintmark="S"
    )
    ledger.add_coin(composition_id=clad, denomination="dime")  # no mint, no series

    rep = build_appraisal_report(ledger.conn)

    mints = {g["mintmark"]: g for g in rep["groups"]["mints"]}
    assert mints["S"]["count"] == 2
    assert mints["S"]["value_cents"] == SILVER_DOLLAR_MELT + 25
    assert mints["(none)"]["count"] == 1
    assert mints["(none)"]["value_cents"] == 10

    series = {g["series"]: g for g in rep["groups"]["series"]}
    assert series["Morgan"]["value_cents"] == SILVER_DOLLAR_MELT
    assert series["(unattributed)"]["count"] == 1

    metals = {g["metal"]: g for g in rep["groups"]["metals"]}
    assert metals["XAG"]["count"] == 1
    assert metals["XAG"]["melt_cents"] == SILVER_DOLLAR_MELT
    assert metals["XAG"]["value_cents"] == SILVER_DOLLAR_MELT
    assert metals["base"]["count"] == 2  # two clad coins
    assert metals["base"]["melt_cents"] == 0
    assert metals["base"]["value_cents"] == 35  # 25 + 10
    # sorted by value descending
    assert rep["groups"]["metals"][0]["metal"] == "XAG"


def test_paired_gain_loss_math(ledger):
    # 13. gain/loss only over coins having BOTH cost basis AND a best value.
    comp = _comp_id(ledger.conn, "Cupronickel clad")
    # paired: face 100, cost 60 -> +40
    ledger.add_coin(composition_id=comp, denomination="dollar", cost_basis_cents=60)
    # cost basis but UNVALUED (no value) -> excluded from paired
    ledger.add_coin(cost_basis_cents=1000)
    # valued but no cost basis -> excluded from paired
    ledger.add_coin(composition_id=comp, denomination="quarter")

    rep = build_appraisal_report(ledger.conn)

    t = rep["totals"]
    assert t["cost_basis_count"] == 2
    assert t["cost_basis_total_cents"] == 1060
    assert t["paired_cost_cents"] == 60
    assert t["paired_best_cents"] == 100
    assert t["gain_loss_cents"] == 40


def test_empty_database_valid_report(ledger):
    # 14. empty DB -> valid report, all zeros/empties.
    rep = build_appraisal_report(ledger.conn)

    assert rep["totals"]["coin_count"] == 0
    assert rep["totals"]["best_total_cents"] == 0
    assert rep["totals"]["gain_loss_cents"] == 0
    assert rep["spot"] == {}
    assert rep["highlights"] == []
    assert rep["groups"] == {
        "sets": [],
        "mints": [],
        "series": [],
        "metals": [],
        "rolls": [],
    }
    assert rep["data_quality"]["metals_missing_spot"] == []
    assert isinstance(rep["generated_at"], str)


def test_report_performs_no_writes(ledger):
    # 15. pure read: total_changes must not move across a report build.
    comp = _comp_id(ledger.conn, "90% silver dollar")
    _insert_spot(ledger.conn, "XAG", 6001)
    ledger.add_coin(composition_id=comp, denomination="dollar", value_basis="melt")

    before = ledger.conn.total_changes
    build_appraisal_report(ledger.conn)
    assert ledger.conn.total_changes == before


def test_location_path_matches_ledger(ledger):
    # location_path replicates Ledger.location_path exactly.
    comp = _comp_id(ledger.conn, "Cupronickel clad")
    box = ledger.create_location("box", "Box A")
    slot = ledger.create_location("slot", "Slot 3", parent=box)
    acc = ledger.add_coin(composition_id=comp, denomination="quarter", location_id=slot)

    rep = build_appraisal_report(ledger.conn)
    (h,) = [h for h in rep["highlights"] if h["accession_no"] == acc]
    assert h["location_path"] == ledger.location_path(slot) == "Box A > Slot 3"
