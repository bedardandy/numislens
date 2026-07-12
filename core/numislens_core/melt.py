"""Spot price fetching, validation, and melt-value recomputation."""

from __future__ import annotations

import json
import socket
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

METALS = frozenset({"XAU", "XAG", "XPT"})
GOLD_API_METAL = {"XAU": "XAU", "XAG": "XAG", "XPT": "XPT"}
YAHOO_SYMBOL = {"XAU": "GC=F", "XAG": "SI=F", "XPT": "PL=F"}
PRIMARY_SOURCE = "gold-api"
CROSSCHECK_SOURCE = "yahoo"
DISAGREE_PCT = 2.0
STALE_HOURS = 48
HTTP_TIMEOUT = 10
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


def update_melt_values(conn: sqlite3.Connection) -> dict:
    updated: list[dict] = []
    hybrid_floors: list[dict] = []
    skipped_no_spot: list[str] = []
    metals_priced: dict[str, int] = {}

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
                    SET value_est_cents = ?, last_appraised = ?
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

    return {
        "updated": updated,
        "hybrid_floors": hybrid_floors,
        "skipped_no_spot": skipped_no_spot,
        "metals_priced": metals_priced,
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
