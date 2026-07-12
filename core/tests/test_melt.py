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
    assert coin["last_appraised"] is not None
    assert summary["updated"] == [
        {"accession": accession, "melt_cents": 4641}
    ]


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
