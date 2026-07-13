"""Coin rolls: bulk same-denomination holdings tracked until pulled apart.

A roll is a stack of like coins (e.g. a $10 bank roll of 50 cents) held as one
unit. Its ``count`` decrements as coins are pulled out and promoted to
individual coin rows; when it hits zero the roll is ``exhausted``. Pure
connection-based module in the shape of :mod:`report` -- it does NOT extend the
Ledger class.

The platform's NO-FABRICATION rule carries through: a roll's face value exists
only for a US coin in the canonical FACE_CENTS map, and its melt value only when
its composition carries a precious weight + metal AND a primary spot row exists.
A roll with neither basis is UNVALUED -- counted and disclosed, never guessed.

Mutations are append-logged to the append-only ``events`` table with
``coin_id`` NULL and an ``event_type`` like ``roll:created`` / ``roll:pulled``;
the ``detail`` JSON always carries the ``roll_no``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from . import melt
from .report import face_value_cents

# Standard mint/bank roll counts keyed by the canonical denomination strings
# (same keys as report.FACE_CENTS / quickadd's denomination words). A roll whose
# count differs from its denomination's standard is flagged ``nonstandard`` --
# informational only, it never suppresses valuation.
STANDARD_ROLL_COUNTS = {
    "cent": 50,
    "nickel": 40,
    "dime": 50,
    "quarter": 40,
    "half dollar": 20,
    "dollar": 25,
}

ROLL_STATUSES = ("unopened", "searching", "searched", "exhausted")


class RollError(Exception):
    pass


class RollNotFound(RollError):
    def __init__(self, roll_no: str) -> None:
        self.roll_no = roll_no
        super().__init__(f"roll not found: {roll_no}")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_roll_no(conn: sqlite3.Connection) -> str:
    """Next 'NR-000001'-style roll number (own sequence, mirrors NL- accessions).

    Scans MAX over the numeric tail of ``rolls.roll_no`` exactly as
    ``Ledger.add_coin`` derives the next NL- accession. ``substr(roll_no, 4)``
    strips the 3-char ``NR-`` prefix.
    """
    row = conn.execute(
        """
        SELECT 1 + COALESCE(MAX(CAST(substr(roll_no, 4) AS INTEGER)), 0)
        FROM rolls
        """
    ).fetchone()
    return "NR-%06d" % row[0]


def _resolve_composition(conn: sqlite3.Connection, composition_name: str | None) -> int | None:
    if composition_name is None:
        return None
    row = conn.execute(
        "SELECT id FROM compositions WHERE name = ?", (composition_name,)
    ).fetchone()
    if row is None:
        raise RollError(f"unknown composition: {composition_name!r}")
    return row["id"]


def _roll_row(conn: sqlite3.Connection, roll_no: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM rolls WHERE roll_no = ?", (roll_no,)
    ).fetchone()
    if row is None:
        raise RollNotFound(roll_no)
    return row


def roll_valuation(
    conn: sqlite3.Connection,
    roll,
    spot_cents_by_metal: dict[str, int],
) -> dict:
    """Value a roll: face (count x FACE_CENTS) and melt (count x per-coin melt).

    ``roll`` is a row/dict carrying at least ``denomination``, ``country``,
    ``count`` and ``composition_id``. Metal + precious weight are looked up from
    the composition. ``spot_cents_by_metal`` supplies primary spot per metal; a
    metal absent from it yields melt None (no fabrication).

    Melt accumulation choice: ``melt_cents = round(count * ozt * spot_cents)`` --
    a single round of the whole-roll product. This is the simplest defensible
    choice and matches how :func:`melt.portfolio_melt` rounds an aggregate; it
    can differ from ``count * round(ozt * spot)`` by up to ~count/2 cents, which
    is immaterial against melt figures and keeps one rounding boundary.

    Returns ``face_cents``, ``melt_cents``, ``best_cents``, ``basis``
    ('melt'|'face'|None; melt wins ties, mirroring the report's priority), and
    ``nonstandard`` (bool: count != the denomination's standard roll count).
    """
    denomination = roll["denomination"]
    country = roll["country"]
    count = roll["count"]
    composition_id = roll["composition_id"]

    # --- face: only for US + a known denomination, times the coin count.
    per_coin_face = face_value_cents(denomination, country)
    face_cents = per_coin_face * count if per_coin_face is not None else None

    # --- melt: composition precious weight + metal + a primary spot all required.
    metal = None
    ozt = None
    if composition_id is not None:
        comp = conn.execute(
            "SELECT metal, precious_weight_ozt FROM compositions WHERE id = ?",
            (composition_id,),
        ).fetchone()
        if comp is not None:
            metal = comp["metal"]
            ozt = comp["precious_weight_ozt"]

    melt_cents = None
    if ozt is not None and metal is not None:
        spot_cents = spot_cents_by_metal.get(metal)
        if spot_cents is not None:
            melt_cents = round(count * ozt * spot_cents)

    # --- best: max of the present candidates; ties broken melt (2) > face (1).
    candidates: list[tuple[int, int, str]] = []
    if melt_cents is not None:
        candidates.append((melt_cents, 2, "melt"))
    if face_cents is not None:
        candidates.append((face_cents, 1, "face"))
    best_cents: int | None = None
    basis: str | None = None
    if candidates:
        best_cents, _prio, basis = max(candidates, key=lambda t: (t[0], t[1]))

    denom_key = denomination.strip().lower() if denomination else None
    nonstandard = count != STANDARD_ROLL_COUNTS.get(denom_key)

    return {
        "face_cents": face_cents,
        "melt_cents": melt_cents,
        "best_cents": best_cents,
        "basis": basis,
        "nonstandard": nonstandard,
    }


def _serialize_roll(
    conn: sqlite3.Connection,
    row,
    spot_cents_by_metal: dict[str, int] | None = None,
) -> dict:
    """Roll row -> dict with composition_name + computed valuation fields.

    When ``spot_cents_by_metal`` is not supplied, the roll's own composition
    metal is priced against the latest primary spot (``melt.latest_spot_cents``)
    so a standalone serialization still values melt when it legitimately can.
    """
    out = dict(row)

    composition_name = None
    metal = None
    if out.get("composition_id") is not None:
        comp = conn.execute(
            "SELECT name, metal FROM compositions WHERE id = ?",
            (out["composition_id"],),
        ).fetchone()
        if comp is not None:
            composition_name = comp["name"]
            metal = comp["metal"]
    out["composition_name"] = composition_name

    if spot_cents_by_metal is None:
        spot_cents_by_metal = {}
        if metal is not None:
            spot_cents = melt.latest_spot_cents(conn, metal, melt.PRIMARY_SOURCE)
            if spot_cents is not None:
                spot_cents_by_metal[metal] = spot_cents

    val = roll_valuation(conn, out, spot_cents_by_metal)
    out["face_cents"] = val["face_cents"]
    out["melt_cents"] = val["melt_cents"]
    out["best_cents"] = val["best_cents"]
    out["basis"] = val["basis"]
    out["nonstandard"] = val["nonstandard"]
    return out


def create_roll(
    conn: sqlite3.Connection,
    denomination: str,
    count: int,
    *,
    country: str = "US",
    series: str | None = None,
    year: int | None = None,
    composition_name: str | None = None,
    variant: str | None = None,
    cost_basis_cents: int | None = None,
    acquired_date: str | None = None,
    acquired_source: str | None = None,
    location_id: int | None = None,
    notes: str | None = None,
) -> dict:
    """Create a roll and return its full serialized dict.

    ``count`` must be >= 1 (a roll is created with coins in it). A supplied
    ``composition_name`` must match ``compositions.name`` exactly, else
    RollError (never guess a composition). Logs a ``roll:created`` event.
    """
    if not isinstance(count, int) or count < 1:
        raise RollError("count must be an integer >= 1")
    if cost_basis_cents is not None and not isinstance(cost_basis_cents, int):
        raise RollError("cost_basis_cents must be an int")
    composition_id = _resolve_composition(conn, composition_name)

    now = _utcnow()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        roll_no = next_roll_no(conn)
        conn.execute(
            """
            INSERT INTO rolls (
                roll_no, denomination, country, count, series, year,
                composition_id, variant, cost_basis_cents, acquired_date,
                acquired_source, location_id, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                roll_no,
                denomination,
                country,
                count,
                series,
                year,
                composition_id,
                variant,
                cost_basis_cents,
                acquired_date,
                acquired_source,
                location_id,
                notes,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO events (coin_id, event_type, at, detail)
            VALUES (NULL, 'roll:created', ?, ?)
            """,
            (now, json.dumps({"roll_no": roll_no, "denomination": denomination, "count": count})),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return _serialize_roll(conn, _roll_row(conn, roll_no))


def get_roll(conn: sqlite3.Connection, roll_no: str) -> dict | None:
    """Serialized roll dict, or None when no roll has that number."""
    row = conn.execute(
        "SELECT * FROM rolls WHERE roll_no = ?", (roll_no,)
    ).fetchone()
    if row is None:
        return None
    return _serialize_roll(conn, row)


def list_rolls(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """All rolls (optionally filtered by status), ordered by roll_no."""
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM rolls WHERE status = ? ORDER BY roll_no", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM rolls ORDER BY roll_no").fetchall()
    return [_serialize_roll(conn, row) for row in rows]


def update_roll(
    conn: sqlite3.Connection,
    roll_no: str,
    *,
    status: str | None = None,
    location_id: int | None = None,
    notes: str | None = None,
    variant: str | None = None,
) -> dict:
    """Update the mutable roll fields (status/location/notes/variant only).

    Logs a ``roll:updated`` event listing the changed fields. RollNotFound when
    the roll is unknown; RollError on an invalid status.
    """
    row = _roll_row(conn, roll_no)
    if status is not None and status not in ROLL_STATUSES:
        raise RollError(f"invalid status: {status!r}")

    provided = {
        "status": status,
        "location_id": location_id,
        "notes": notes,
        "variant": variant,
    }
    changed = {k: v for k, v in provided.items() if v is not None and row[k] != v}

    if changed:
        now = _utcnow()
        set_clause = ", ".join(f"{k} = ?" for k in changed)
        params = [*changed.values(), roll_no]
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                f"UPDATE rolls SET {set_clause} WHERE roll_no = ?", params
            )
            conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (NULL, 'roll:updated', ?, ?)
                """,
                (now, json.dumps({"roll_no": roll_no, "changed": changed})),
            )

    return _serialize_roll(conn, _roll_row(conn, roll_no))


def pull_from_roll(conn: sqlite3.Connection, roll_no: str, count: int) -> dict:
    """Pull ``count`` coins out of a roll, decrementing its remaining count.

    RollNotFound when unknown; RollError when ``count`` < 1 or exceeds the
    remaining count. When the remaining count reaches 0 the status flips to
    ``exhausted`` automatically. Logs a ``roll:pulled`` event. Coin rows for the
    pulled coins are created by the API layer (via quickadd), not here.
    """
    row = _roll_row(conn, roll_no)
    if not isinstance(count, int) or count < 1:
        raise RollError("pull count must be an integer >= 1")
    remaining = row["count"]
    if count > remaining:
        raise RollError(
            f"cannot pull {count} from {roll_no}: only {remaining} remaining"
        )

    new_count = remaining - count
    new_status = "exhausted" if new_count == 0 else row["status"]
    now = _utcnow()
    with conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "UPDATE rolls SET count = ?, status = ? WHERE roll_no = ?",
            (new_count, new_status, roll_no),
        )
        conn.execute(
            """
            INSERT INTO events (coin_id, event_type, at, detail)
            VALUES (NULL, 'roll:pulled', ?, ?)
            """,
            (
                now,
                json.dumps(
                    {"roll_no": roll_no, "pulled": count, "remaining": new_count}
                ),
            ),
        )

    return _serialize_roll(conn, _roll_row(conn, roll_no))
