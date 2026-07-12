"""Tests for value-watch staleness plumbing (Phase 6)."""

from datetime import datetime, timezone

import pytest

from numislens_core.ledger import CoinNotFound, UnknownSeries
from numislens_core.melt import update_melt_values


def _insert_spot(conn, metal, price_cents, *, source="gold-api", fetched_at=None):
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (metal, price_cents, source, fetched_at),
    )
    conn.commit()


def _silver_dollar_comp_id(conn):
    row = conn.execute(
        "SELECT id FROM compositions WHERE name = '90% silver dollar'"
    ).fetchone()
    return row["id"]


# --- mark_stale -----------------------------------------------------------


def test_mark_stale_by_accessions(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1921)
    a2 = ledger.add_coin(series="Peace Dollar", year=1922)
    count = ledger.mark_stale(accessions=[a1], reason="auction record")
    assert count == 1
    assert ledger.get_coin(a1)["stale_reason"] == "auction record"
    assert ledger.get_coin(a1)["stale_since"] is not None
    assert ledger.get_coin(a2)["stale_since"] is None


def test_mark_stale_unknown_accession_fails_loud(ledger):
    ledger.add_coin(series="Morgan Dollar", year=1921)
    with pytest.raises(CoinNotFound):
        ledger.mark_stale(accessions=["NL-999999"], reason="x")


def test_mark_stale_by_series_case_insensitive(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1878)
    a2 = ledger.add_coin(series="Morgan Dollar", year=1921)
    a3 = ledger.add_coin(series="Peace Dollar", year=1921)
    count = ledger.mark_stale(series="morgan dollar", reason="silver news")
    assert count == 2
    assert ledger.get_coin(a1)["stale_since"] is not None
    assert ledger.get_coin(a2)["stale_since"] is not None
    assert ledger.get_coin(a3)["stale_since"] is None


def test_mark_stale_unknown_series_lists_known(ledger):
    ledger.add_coin(series="Morgan Dollar", year=1921)
    ledger.add_coin(series="Peace Dollar", year=1921)
    with pytest.raises(UnknownSeries) as exc:
        ledger.mark_stale(series="Barber Dime", reason="x")
    assert exc.value.series == "Barber Dime"
    assert set(exc.value.known) == {"Morgan Dollar", "Peace Dollar"}


def test_mark_stale_by_set_id(ledger, tmp_path):
    import json

    manifest = {
        "id": "mini-set",
        "name": "Mini Set",
        "series": "Morgan Dollar",
        "composition_ref": "90% silver dollar",
        "slots": [
            {"year": 1878, "mint": "P"},
            {"year": 1879, "mint": "P"},
        ],
    }
    mpath = tmp_path / "mini.json"
    mpath.write_text(json.dumps(manifest))
    set_id = ledger.load_set_manifest(mpath)
    a1 = ledger.add_coin(series="Morgan Dollar", year=1878, mintmark="P")
    ledger.assign_to_slot(set_id, {"year": 1878, "mint": "P"}, a1)
    # a2 is same series but NOT assigned to a slot.
    a2 = ledger.add_coin(series="Morgan Dollar", year=1921, mintmark="P")

    count = ledger.mark_stale(set_id=set_id, reason="set premium")
    assert count == 1
    assert ledger.get_coin(a1)["stale_since"] is not None
    assert ledger.get_coin(a2)["stale_since"] is None


def test_mark_stale_requires_exactly_one_target(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1921)
    with pytest.raises(ValueError, match="exactly one"):
        ledger.mark_stale(accessions=[a1], series="Morgan Dollar", reason="x")
    with pytest.raises(ValueError, match="exactly one"):
        ledger.mark_stale(reason="x")


def test_mark_stale_requires_reason(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1921)
    with pytest.raises(ValueError, match="reason"):
        ledger.mark_stale(accessions=[a1], reason="")


# --- clear on appraisal ---------------------------------------------------


def test_record_appraisal_clears_staleness(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1921)
    ledger.mark_stale(accessions=[a1], reason="silver moved")
    assert ledger.get_coin(a1)["stale_since"] is not None

    ledger.record_appraisal(a1, "human", value_cents=5000, value_basis="numismatic")
    coin = ledger.get_coin(a1)
    assert coin["stale_since"] is None
    assert coin["stale_reason"] is None
    assert coin["value_est_cents"] == 5000


# --- list_stale / watchlist ----------------------------------------------


def test_list_stale(ledger):
    a1 = ledger.add_coin(series="Morgan Dollar", year=1921)
    ledger.add_coin(series="Peace Dollar", year=1922)
    ledger.mark_stale(accessions=[a1], reason="r")
    stale = ledger.list_stale()
    assert [c["accession_no"] for c in stale] == [a1]
    assert stale[0]["stale_reason"] == "r"


def test_watchlist_top_n_by_value_ties_by_accession(ledger):
    a1 = ledger.add_coin(series="A", value_est_cents=1000)
    a2 = ledger.add_coin(series="B", value_est_cents=5000)
    a3 = ledger.add_coin(series="C", value_est_cents=5000)  # tie with a2
    watch = ledger.watchlist(2)
    # 5000s first, tie broken by accession (a2 < a3); a1 (1000) excluded by n=2.
    assert [c["accession_no"] for c in watch] == [a2, a3]
    assert a1 not in [c["accession_no"] for c in watch]


def test_watchlist_excludes_null_value(ledger):
    priced = ledger.add_coin(series="A", value_est_cents=1000)
    ledger.add_coin(series="B")  # no value -> unappraised, not watchable
    watch = ledger.watchlist(25)
    assert [c["accession_no"] for c in watch] == [priced]


# --- spot-move staleness trigger -----------------------------------------


def test_spot_move_10pct_marks_hybrid_and_numismatic_not_melt(ledger):
    comp = _silver_dollar_comp_id(ledger.conn)
    melt_coin = ledger.add_coin(composition_id=comp, value_basis="melt")
    hybrid_coin = ledger.add_coin(composition_id=comp, value_basis="hybrid")
    num_coin = ledger.add_coin(composition_id=comp, value_basis="numismatic")

    # Prior primary row, then a +12% jump.
    _insert_spot(ledger.conn, "XAG", 6000, fetched_at="2026-07-11T12:00:00+00:00")
    _insert_spot(ledger.conn, "XAG", 6720, fetched_at="2026-07-12T12:00:00+00:00")

    summary = update_melt_values(ledger.conn)

    assert ledger.get_coin(hybrid_coin)["stale_since"] is not None
    assert ledger.get_coin(num_coin)["stale_since"] is not None
    # Melt-basis coin reprices automatically; it is NEVER flagged stale.
    assert ledger.get_coin(melt_coin)["stale_since"] is None
    marked = {s["accession"] for s in summary["stale_marked"]}
    assert marked == {hybrid_coin, num_coin}
    reason = ledger.get_coin(hybrid_coin)["stale_reason"]
    assert "XAG" in reason and "%" in reason


def test_spot_move_under_10pct_no_trigger(ledger):
    comp = _silver_dollar_comp_id(ledger.conn)
    hybrid_coin = ledger.add_coin(composition_id=comp, value_basis="hybrid")
    _insert_spot(ledger.conn, "XAG", 6000, fetched_at="2026-07-11T12:00:00+00:00")
    _insert_spot(ledger.conn, "XAG", 6300, fetched_at="2026-07-12T12:00:00+00:00")  # +5%

    summary = update_melt_values(ledger.conn)
    assert ledger.get_coin(hybrid_coin)["stale_since"] is None
    assert summary["stale_marked"] == []


def test_spot_first_row_no_prior_no_trigger(ledger):
    comp = _silver_dollar_comp_id(ledger.conn)
    hybrid_coin = ledger.add_coin(composition_id=comp, value_basis="hybrid")
    _insert_spot(ledger.conn, "XAG", 6000)  # only one primary row

    summary = update_melt_values(ledger.conn)
    assert ledger.get_coin(hybrid_coin)["stale_since"] is None
    assert summary["stale_marked"] == []
