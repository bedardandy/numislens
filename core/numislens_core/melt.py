"""Spot price fetching, validation, and melt-value recomputation."""

from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_log = logging.getLogger(__name__)

METALS = frozenset({"XAU", "XAG", "XPT"})
GOLD_API_METAL = {"XAU": "XAU", "XAG": "XAG", "XPT": "XPT"}
YAHOO_SYMBOL = {"XAU": "GC=F", "XAG": "SI=F", "XPT": "PL=F"}
PRIMARY_SOURCE = "gold-api"
CROSSCHECK_SOURCE = "yahoo"
DISAGREE_PCT = 2.0
STALE_HOURS = 48
HTTP_TIMEOUT = 10

# Value-watch (Phase 6) thresholds.
# A >=10% move in the PRIMARY spot for a metal marks every hybrid/numismatic
# coin of that metal stale (their premiums track spot; melt-basis coins just
# reprice and need no flag). A >3% day-over-day move (or any newly-stale coin)
# triggers the optional ntfy push. NUMISLENS_NTFY_URL is a full ntfy.sh topic
# URL; when unset, no push is attempted.
STALE_SPOT_PCT = 10.0
DAILY_ALERT_PCT = 3.0
NTFY_ENV = "NUMISLENS_NTFY_URL"
NTFY_TIMEOUT = 5
# Yahoo 429s the ubiquitous "Chrome/120.0.0.0" scraper UA; this shorter UA passes.
YAHOO_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


class SpotError(Exception):
    pass


class SpotDisagreement(SpotError):
    def __init__(
        self,
        metal: str,
        primary_cents: int,
        crosscheck_cents: int,
        pct: float,
    ) -> None:
        self.metal = metal
        self.primary_cents = primary_cents
        self.crosscheck_cents = crosscheck_cents
        self.pct = pct
        super().__init__(
            f"spot disagreement for {metal}: primary={primary_cents}c "
            f"crosscheck={crosscheck_cents}c diff={pct:.2f}%"
        )


class SpotStale(SpotError):
    def __init__(self, metal: str, primary_updated_at: str, age_hours: float) -> None:
        self.metal = metal
        self.primary_updated_at = primary_updated_at
        self.age_hours = age_hours
        super().__init__(
            f"stale spot for {metal}: updatedAt={primary_updated_at} "
            f"age={age_hours:.1f}h"
        )


class SpotFetchError(SpotError):
    pass


@dataclass(frozen=True)
class SpotQuote:
    metal: str
    primary_cents: int
    crosscheck_cents: int
    primary_updated_at: str
    fetched_at: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_ts(iso_ts: str) -> datetime:
    if iso_ts.endswith("Z"):
        iso_ts = iso_ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(iso_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            raw = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as exc:
        raise SpotFetchError(f"HTTP request failed for {url}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpotFetchError(f"invalid JSON from {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise SpotFetchError(f"expected JSON object from {url}, got {type(data).__name__}")
    return data


def _fetch_gold_api(metal: str) -> tuple[int, str]:
    symbol = GOLD_API_METAL[metal]
    url = f"https://api.gold-api.com/price/{symbol}"
    data = _http_get_json(url)
    price = data.get("price")
    updated_at = data.get("updatedAt")
    if not isinstance(price, (int, float)):
        raise SpotFetchError(
            f"gold-api missing or non-numeric price for {metal}: {price!r}"
        )
    if not isinstance(updated_at, str) or not updated_at:
        raise SpotFetchError(
            f"gold-api missing updatedAt for {metal}: {updated_at!r}"
        )
    return round(price * 100), updated_at


def _fetch_yahoo(metal: str) -> int:
    symbol = YAHOO_SYMBOL[metal]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": YAHOO_USER_AGENT}
    data = _http_get_json(url, headers=headers)
    try:
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SpotFetchError(
            f"yahoo chart missing regularMarketPrice for {metal}"
        ) from exc
    if not isinstance(price, (int, float)):
        raise SpotFetchError(
            f"yahoo non-numeric regularMarketPrice for {metal}: {price!r}"
        )
    return round(price * 100)


def _pct_diff(a_cents: int, b_cents: int) -> float:
    if a_cents == 0 and b_cents == 0:
        raise SpotFetchError("cannot compute percent diff when both prices are zero")
    midpoint = (a_cents + b_cents) / 2.0
    return 100.0 * abs(a_cents - b_cents) / midpoint


def _hours_since(iso_ts: str, now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    dt = _parse_iso_ts(iso_ts)
    return (now - dt).total_seconds() / 3600.0


def fetch_spot(metal: str) -> SpotQuote:
    if metal not in METALS:
        raise ValueError(f"invalid metal: {metal!r}")
    primary_cents, primary_updated_at = _fetch_gold_api(metal)
    crosscheck_cents = _fetch_yahoo(metal)
    age_hours = _hours_since(primary_updated_at)
    if age_hours > STALE_HOURS:
        raise SpotStale(metal, primary_updated_at, age_hours)
    pct = _pct_diff(primary_cents, crosscheck_cents)
    if pct > DISAGREE_PCT:
        raise SpotDisagreement(metal, primary_cents, crosscheck_cents, pct)
    return SpotQuote(
        metal=metal,
        primary_cents=primary_cents,
        crosscheck_cents=crosscheck_cents,
        primary_updated_at=primary_updated_at,
        fetched_at=_utcnow(),
    )


def record_spot(
    conn: sqlite3.Connection,
    metal: str,
    quote: SpotQuote | None = None,
) -> None:
    if quote is None:
        quote = fetch_spot(metal)
    with conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT OR IGNORE INTO spot_prices
                (metal, price_usd_cents, source, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (quote.metal, quote.primary_cents, PRIMARY_SOURCE, quote.fetched_at),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO spot_prices
                (metal, price_usd_cents, source, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (quote.metal, quote.crosscheck_cents, CROSSCHECK_SOURCE, quote.fetched_at),
        )


def latest_spot_cents(
    conn: sqlite3.Connection,
    metal: str,
    source: str = PRIMARY_SOURCE,
) -> int | None:
    row = conn.execute(
        """
        SELECT price_usd_cents FROM spot_prices
        WHERE metal = ? AND source = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (metal, source),
    ).fetchone()
    if row is None:
        return None
    return row["price_usd_cents"]


def latest_spot(
    conn: sqlite3.Connection,
    metal: str,
    source: str = PRIMARY_SOURCE,
) -> dict | None:
    row = conn.execute(
        """
        SELECT price_usd_cents, source, fetched_at FROM spot_prices
        WHERE metal = ? AND source = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (metal, source),
    ).fetchone()
    if row is None:
        return None
    return {
        "price_usd_cents": row["price_usd_cents"],
        "source": row["source"],
        "fetched_at": row["fetched_at"],
    }


def _primary_spot_move(conn: sqlite3.Connection, metal: str) -> float | None:
    """Percent move of the latest PRIMARY spot vs the previous primary row.

    Returns None when there is no prior row to compare against (first ever spot
    for the metal) or the prior price is zero. Positive = up.
    """
    rows = conn.execute(
        """
        SELECT price_usd_cents FROM spot_prices
        WHERE metal = ? AND source = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 2
        """,
        (metal, PRIMARY_SOURCE),
    ).fetchall()
    if len(rows) < 2:
        return None
    latest = rows[0]["price_usd_cents"]
    prior = rows[1]["price_usd_cents"]
    if prior == 0:
        return None
    return 100.0 * (latest - prior) / prior


def update_melt_values(conn: sqlite3.Connection) -> dict:
    updated: list[dict] = []
    hybrid_floors: list[dict] = []
    skipped_no_spot: list[str] = []
    metals_priced: dict[str, int] = {}
    stale_marked: list[dict] = []

    rows = conn.execute(
        """
        SELECT
            c.accession_no,
            c.value_basis,
            comp.metal,
            comp.precious_weight_ozt
        FROM coins c
        INNER JOIN compositions comp ON c.composition_id = comp.id
        WHERE comp.precious_weight_ozt IS NOT NULL
        ORDER BY c.accession_no
        """
    ).fetchall()

    spot_cache: dict[str, int | None] = {}
    now = _utcnow()

    with conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for row in rows:
            metal = row["metal"]
            if metal is None:
                continue
            if metal not in spot_cache:
                spot_cents = latest_spot_cents(conn, metal, PRIMARY_SOURCE)
                spot_cache[metal] = spot_cents
                if spot_cents is not None:
                    metals_priced[metal] = spot_cents

            spot_cents = spot_cache[metal]
            if spot_cents is None:
                skipped_no_spot.append(row["accession_no"])
                continue

            melt_cents = round(row["precious_weight_ozt"] * spot_cents)
            value_basis = row["value_basis"]

            if value_basis == "melt":
                conn.execute(
                    """
                    UPDATE coins
                    SET value_est_cents = ?, value_refreshed_at = ?
                    WHERE accession_no = ?
                    """,
                    (melt_cents, now, row["accession_no"]),
                )
                updated.append(
                    {"accession": row["accession_no"], "melt_cents": melt_cents}
                )
            elif value_basis == "hybrid":
                hybrid_floors.append(
                    {
                        "accession": row["accession_no"],
                        "melt_floor_cents": melt_cents,
                    }
                )

        # Spot-move staleness trigger: when a metal's primary spot moved >=10%
        # since the previous primary row, every hybrid/numismatic coin of that
        # metal is flagged stale (its premium tracks spot). Melt-basis coins are
        # NOT flagged — they repriced above. Deterministic SQL, no value change.
        for metal, spot_cents in spot_cache.items():
            if spot_cents is None:
                continue
            move = _primary_spot_move(conn, metal)
            if move is None or abs(move) < STALE_SPOT_PCT:
                continue
            reason = f"spot {metal} moved {move:+.1f}%"
            affected = conn.execute(
                """
                SELECT accession_no, stale_since FROM coins
                WHERE value_basis IN ('hybrid', 'numismatic')
                  AND composition_id IN (
                    SELECT id FROM compositions WHERE metal = ?
                  )
                ORDER BY accession_no
                """,
                (metal,),
            ).fetchall()
            if not affected:
                continue
            conn.execute(
                """
                UPDATE coins SET stale_since = ?, stale_reason = ?
                WHERE value_basis IN ('hybrid', 'numismatic')
                  AND composition_id IN (
                    SELECT id FROM compositions WHERE metal = ?
                  )
                """,
                (now, reason, metal),
            )
            for arow in affected:
                stale_marked.append(
                    {
                        "accession": arow["accession_no"],
                        "reason": reason,
                        "newly": arow["stale_since"] is None,
                    }
                )

    return {
        "updated": updated,
        "hybrid_floors": hybrid_floors,
        "skipped_no_spot": skipped_no_spot,
        "metals_priced": metals_priced,
        "stale_marked": stale_marked,
    }


def portfolio_melt(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT
            comp.metal AS metal,
            SUM(ROUND(comp.precious_weight_ozt * sp.price_usd_cents)) AS melt_cents
        FROM coins c
        INNER JOIN compositions comp ON c.composition_id = comp.id
        INNER JOIN spot_prices sp
            ON sp.metal = comp.metal AND sp.source = ?
        WHERE comp.precious_weight_ozt IS NOT NULL
          AND comp.metal IS NOT NULL
          AND sp.id = (
            SELECT id FROM spot_prices
            WHERE metal = comp.metal AND source = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
          )
        GROUP BY comp.metal
        """,
        (PRIMARY_SOURCE, PRIMARY_SOURCE),
    ).fetchall()

    by_metal = {row["metal"]: int(row["melt_cents"]) for row in rows}
    return {
        "total_cents": sum(by_metal.values()),
        "by_metal": by_metal,
    }


def portfolio_value(conn: sqlite3.Connection) -> dict:
    """Portfolio valuation: melt (total + per-metal) and estimated value sums.

    Pure read aggregation. ``melt`` reuses :func:`portfolio_melt`; the estimated
    numismatic/hybrid value is summed from ``coins.value_est_cents`` grouped by
    ``value_basis`` (a NULL basis is bucketed as ``"unspecified"``).
    """
    melt = portfolio_melt(conn)
    rows = conn.execute(
        """
        SELECT value_basis, COUNT(*) AS n, COALESCE(SUM(value_est_cents), 0) AS s
        FROM coins
        WHERE value_est_cents IS NOT NULL
        GROUP BY value_basis
        """
    ).fetchall()
    by_basis: dict[str, dict] = {}
    for row in rows:
        basis = row["value_basis"] or "unspecified"
        by_basis[basis] = {"count": row["n"], "value_cents": int(row["s"])}
    value_est_total_cents = sum(v["value_cents"] for v in by_basis.values())
    return {
        "melt": melt,
        "value_est_by_basis": by_basis,
        "value_est_total_cents": value_est_total_cents,
    }


def _post_ntfy(url: str, message: str, timeout: float = NTFY_TIMEOUT) -> None:
    request = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def build_notification(conn: sqlite3.Connection, summary: dict) -> str | None:
    """Compose the ntfy body, or None when nothing crosses a threshold.

    Triggers: any metal's day-over-day |delta| > 3% (from :func:`melt_delta`),
    or one or more coins NEWLY marked stale by the >=10% spot-move trigger in
    ``summary``. Pure/read-only — no network.
    """
    lines: list[str] = []
    delta = melt_delta(conn)
    for metal in sorted(delta):
        pct = delta[metal]["pct"]
        if abs(pct) > DAILY_ALERT_PCT:
            lines.append(f"{metal} spot {pct:+.1f}% day-over-day")
    newly = [s for s in summary.get("stale_marked", []) if s.get("newly")]
    if newly:
        lines.append(f"{len(newly)} coin(s) newly stale (spot moved >=10%)")
    if not lines:
        return None
    return "NumisLens value-watch: " + "; ".join(lines)


def push_notification(
    conn: sqlite3.Connection,
    summary: dict,
    *,
    url: str | None = None,
) -> str | None:
    """Send an ntfy push if configured and a threshold is crossed.

    ``url`` defaults to the ``NUMISLENS_NTFY_URL`` env var (a full ntfy.sh topic
    URL). Returns the message sent, or None (unset, or nothing to report).

    A notification failure is LOGGED, never raised — a dead notifier must not
    block the melt update or the ledger. This is the one deliberately non-fatal
    outbound error path in core (see AGENTS.md).
    """
    if url is None:
        url = os.environ.get(NTFY_ENV)
    if not url:
        return None
    message = build_notification(conn, summary)
    if message is None:
        return None
    try:
        _post_ntfy(url, message)
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        _log.warning("ntfy notification failed (non-fatal): %s", exc)
        return None
    return message


def melt_delta(conn: sqlite3.Connection, days: int = 1) -> dict:
    result: dict[str, dict] = {}

    for metal in sorted(METALS):
        latest = conn.execute(
            """
            SELECT price_usd_cents, fetched_at FROM spot_prices
            WHERE metal = ? AND source = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (metal, PRIMARY_SOURCE),
        ).fetchone()
        if latest is None:
            continue

        latest_cents = latest["price_usd_cents"]
        latest_day = latest["fetched_at"][:10]
        cutoff_day = (
            datetime.fromisoformat(latest_day).date() - timedelta(days=days)
        ).isoformat()

        prior = conn.execute(
            """
            SELECT price_usd_cents FROM spot_prices
            WHERE metal = ? AND source = ?
              AND substr(fetched_at, 1, 10) <= ?
              AND substr(fetched_at, 1, 10) < ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (metal, PRIMARY_SOURCE, cutoff_day, latest_day),
        ).fetchone()
        if prior is None:
            continue

        prior_cents = prior["price_usd_cents"]
        pct = 100.0 * (latest_cents - prior_cents) / prior_cents
        result[metal] = {
            "latest_cents": latest_cents,
            "prior_cents": prior_cents,
            "pct": pct,
        }

    return result
