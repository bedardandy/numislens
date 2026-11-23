"""Tests for spot price fetching and melt-value recomputation."""

from datetime import datetime, timedelta, timezone

import pytest

from numislens_core import melt
from numislens_core.melt import (
    CROSSCHECK_SOURCE,
    PRIMARY_SOURCE,
    SpotDisagreement,
    SpotFetchError,
    SpotQuote,
    SpotStale,
    fetch_spot,
    latest_spot,
    melt_delta,
    portfolio_melt,
    record_spot,
    update_melt_values,
)

SILVER_DOLLAR_MELT_CENTS = round(0.77344 * 6001)


def _silver_dollar_comp_id(conn):
    row = conn.execute(
        "SELECT id FROM compositions WHERE name = '90% silver dollar'"
    ).fetchone()
    assert row is not None
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


def test_fetch_spot_agreement_returns_quote(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()

    def fake_gold(metal):
        assert metal == "XAG"
        return 6001, now

    def fake_yahoo(metal):
        assert metal == "XAG"
        return 6010

    monkeypatch.setattr(melt, "_fetch_gold_api", fake_gold)
    monkeypatch.setattr(melt, "_fetch_yahoo", fake_yahoo)

    quote = fetch_spot("XAG")
    assert isinstance(quote, SpotQuote)
    assert quote.metal == "XAG"
    assert quote.primary_cents == 6001
    assert quote.crosscheck_cents == 6010
    assert quote.primary_updated_at == now


def test_fetch_spot_disagreement_raises(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(melt, "_fetch_gold_api", lambda metal: (6000, now))
    monkeypatch.setattr(melt, "_fetch_yahoo", lambda metal: 7000)

    with pytest.raises(SpotDisagreement):
        fetch_spot("XAG")


def test_fetch_spot_staleness_raises(monkeypatch):
    stale = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()

    monkeypatch.setattr(melt, "_fetch_gold_api", lambda metal: (6001, stale))
    monkeypatch.setattr(melt, "_fetch_yahoo", lambda metal: 6001)

    with pytest.raises(SpotStale):
        fetch_spot("XAG")


def test_fetch_spot_http_error_raises(monkeypatch):
    def raise_fetch_error(metal):
        raise SpotFetchError("gold-api unavailable")

    monkeypatch.setattr(melt, "_fetch_gold_api", raise_fetch_error)

    with pytest.raises(SpotFetchError):
        fetch_spot("XAG")


def test_fetch_spot_bad_metal_raises_value_error():
    with pytest.raises(ValueError, match="invalid metal"):
        fetch_spot("XXX")


def test_record_spot_inserts_both_rows(ledger):
    fetched_at = datetime.now(timezone.utc).isoformat()
    quote = SpotQuote(
        metal="XAG",
        primary_cents=6001,
        crosscheck_cents=6010,
        primary_updated_at=fetched_at,
        fetched_at=fetched_at,
    )

    record_spot(ledger.conn, "XAG", quote)

    rows = ledger.conn.execute(
        "SELECT metal, price_usd_cents, source, fetched_at FROM spot_prices"
    ).fetchall()
    assert len(rows) == 2
    by_source = {row["source"]: row for row in rows}
    assert by_source[PRIMARY_SOURCE]["price_usd_cents"] == 6001
    assert by_source[PRIMARY_SOURCE]["fetched_at"] == fetched_at
    assert by_source[CROSSCHECK_SOURCE]["price_usd_cents"] == 6010
    assert by_source[CROSSCHECK_SOURCE]["fetched_at"] == fetched_at


def test_latest_spot(ledger):
    fetched_at = "2026-07-12T12:00:00+00:00"
    _insert_spot(ledger.conn, "XAG", 6001, fetched_at=fetched_at)

    result = latest_spot(ledger.conn, "XAG")
    assert result is not None
    assert result["price_usd_cents"] == 6001
    assert result["source"] == PRIMARY_SOURCE
    assert result["fetched_at"] == fetched_at

    assert latest_spot(ledger.conn, "XPT") is None


def test_record_spot_dedup_on_reinsert(ledger):
    fetched_at = datetime.now(timezone.utc).isoformat()
    quote = SpotQuote(
        metal="XAG",
        primary_cents=6001,
        crosscheck_cents=6010,
        primary_updated_at=fetched_at,
        fetched_at=fetched_at,
    )

    record_spot(ledger.conn, "XAG", quote)
    record_spot(ledger.conn, "XAG", quote)

    count = ledger.conn.execute("SELECT COUNT(*) FROM spot_prices").fetchone()[0]
    assert count == 2


def test_update_melt_values_melt_basis_exact_math(ledger):
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)

    accession = ledger.add_coin(
        composition_id=comp_id,
        value_basis="melt",
    )

    summary = update_melt_values(ledger.conn)
    coin = ledger.get_coin(accession)

    assert coin["value_est_cents"] == SILVER_DOLLAR_MELT_CENTS == 4641
    assert coin["value_refreshed_at"] is not None
    assert coin["last_appraised"] is None
    assert summary["updated"] == [
        {"accession": accession, "melt_cents": 4641}
    ]


def test_update_melt_values_never_touches_last_appraised(ledger):
    """Melt repricing is not an appraisal: last_appraised keeps its meaning."""
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)
    accession = ledger.add_coin(composition_id=comp_id, value_basis="melt")

    ledger.record_appraisal(accession, "human", value_cents=123456)
    appraised_at = ledger.get_coin(accession)["last_appraised"]
    assert appraised_at is not None

    update_melt_values(ledger.conn)
    coin = ledger.get_coin(accession)
    # A valued appraisal moved the coin off melt basis, so the daily recompute
    # records only the hybrid floor — the human value and provenance survive.
    assert coin["value_est_cents"] == 123456
    assert coin["last_appraised"] == appraised_at
    assert coin["value_refreshed_at"] is None


def test_valued_appraisal_moves_melt_coin_to_hybrid(ledger):
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)
    accession = ledger.add_coin(composition_id=comp_id, value_basis="melt")

    ledger.record_appraisal(accession, "human", value_cents=123456)
    coin = ledger.get_coin(accession)
    assert coin["value_basis"] == "hybrid"

    summary = update_melt_values(ledger.conn)
    coin = ledger.get_coin(accession)
    assert coin["value_est_cents"] == 123456
    assert {"accession": accession, "melt_floor_cents": SILVER_DOLLAR_MELT_CENTS} in (
        summary["hybrid_floors"]
    )


def test_grade_only_appraisal_keeps_melt_basis(ledger):
    """A grade-only appraisal (no value) must not move a melt coin off melt."""
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)
    accession = ledger.add_coin(composition_id=comp_id, value_basis="melt")

    ledger.record_appraisal(accession, "vision:local-vlm", grade_bucket="VF")
    assert ledger.get_coin(accession)["value_basis"] == "melt"


def test_update_melt_values_hybrid_not_overwritten(ledger):
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)

    accession = ledger.add_coin(
        composition_id=comp_id,
        value_basis="hybrid",
        value_est_cents=999999,
    )

    summary = update_melt_values(ledger.conn)
    coin = ledger.get_coin(accession)

    assert coin["value_est_cents"] == 999999
    assert summary["hybrid_floors"] == [
        {"accession": accession, "melt_floor_cents": 4641}
    ]


def test_update_melt_values_skips_when_no_spot(ledger):
    comp_id = _silver_dollar_comp_id(ledger.conn)

    accession = ledger.add_coin(
        composition_id=comp_id,
        value_basis="melt",
    )

    summary = update_melt_values(ledger.conn)
    coin = ledger.get_coin(accession)

    assert coin["value_est_cents"] is None
    assert summary["skipped_no_spot"] == [accession]


def test_portfolio_melt_totals(ledger):
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 6001)

    ledger.add_coin(composition_id=comp_id, value_basis="melt")
    ledger.add_coin(composition_id=comp_id, value_basis="hybrid")

    result = portfolio_melt(ledger.conn)

    assert result["total_cents"] == 2 * SILVER_DOLLAR_MELT_CENTS
    assert result["by_metal"]["XAG"] == 2 * SILVER_DOLLAR_MELT_CENTS


def test_melt_delta_pct(ledger):
    _insert_spot(
        ledger.conn,
        "XAG",
        6000,
        fetched_at="2026-07-10T12:00:00+00:00",
    )
    _insert_spot(
        ledger.conn,
        "XAG",
        6300,
        fetched_at="2026-07-12T12:00:00+00:00",
    )

    result = melt_delta(ledger.conn)

    assert result["XAG"]["latest_cents"] == 6300
    assert result["XAG"]["prior_cents"] == 6000
    assert result["XAG"]["pct"] == pytest.approx(5.0)


def test_sold_and_discarded_coins_are_not_holdings_for_melt(ledger):
    """Melt recompute and portfolio rollups cover holdings only.

    Regression: a sold melt-basis coin kept being repriced from spot every day
    and kept counting toward portfolio melt / estimated value.
    """
    comp_id = _silver_dollar_comp_id(ledger.conn)
    _insert_spot(ledger.conn, "XAG", 3000)
    kept = ledger.add_coin(composition_id=comp_id, value_basis="melt")
    sold = ledger.add_coin(composition_id=comp_id, value_basis="melt")
    tossed = ledger.add_coin(
        composition_id=comp_id, value_basis="numismatic", value_est_cents=9999
    )
    update_melt_values(ledger.conn)
    sold_value_at_sale = ledger.get_coin(sold)["value_est_cents"]
    ledger.set_disposition(sold, "sold", sold_price_cents=2500)
    ledger.set_disposition(tossed, "discarded")

    _insert_spot(ledger.conn, "XAG", 4000)
    summary = update_melt_values(ledger.conn)

    assert [u["accession"] for u in summary["updated"]] == [kept]
    assert ledger.get_coin(sold)["value_est_cents"] == sold_value_at_sale
    # The +33% spot move flags no coin that has left the collection.
    assert summary["stale_marked"] == []
    assert ledger.get_coin(tossed)["stale_since"] is None

    one_dollar_melt = round(0.77344 * 4000)
    assert portfolio_melt(ledger.conn)["total_cents"] == one_dollar_melt
    pv = melt.portfolio_value(ledger.conn)
    assert pv["value_est_total_cents"] == one_dollar_melt
    assert pv["value_est_by_basis"] == {
        "melt": {"count": 1, "value_cents": one_dollar_melt}
    }
