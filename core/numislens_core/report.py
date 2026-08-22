"""Appraisal-report aggregation: per-coin valuation and portfolio rollups.

Pure read. The platform's hard rule is NO FABRICATION: a value exists only when
its inputs exist. melt needs composition weight + metal + a primary spot row;
collectible needs a numismatic/hybrid (or unspecified-but-present) estimate;
face needs a known US denomination. A coin with none of the three is UNVALUED --
excluded from value totals, but counted and disclosed rather than hidden.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import melt

# US face values in cents, keyed by lowercased denomination. US coins only.
FACE_CENTS = {
    "cent": 1,
    "nickel": 5,
    "dime": 10,
    "quarter": 25,
    "half dollar": 50,
    "dollar": 100,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def face_value_cents(denomination: str | None, country: str | None) -> int | None:
    """Face value in cents for a US coin, else None. Never guesses.

    country must be exactly 'US' (the schema default); NULL/other -> None. The
    denomination is matched case-insensitively after strip(); anything not in
    FACE_CENTS -> None.
    """
    if country != "US":
        return None
    if denomination is None:
        return None
    return FACE_CENTS.get(denomination.strip().lower())


def realized_summary(conn: sqlite3.Connection) -> dict:
    """Realized P&L over coins with disposition='sold'. Pure read.

    proceeds minus cost basis across sold coins; missing inputs are DISCLOSED,
    never imputed — a sold coin without a recorded cost basis widens
    ``missing_cost_count`` rather than silently counting as zero-basis profit.
    """
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS sold_count,
            COALESCE(SUM(sold_price_cents), 0) AS proceeds_cents,
            COALESCE(SUM(cost_basis_cents), 0) AS cost_basis_cents,
            SUM(CASE WHEN cost_basis_cents IS NULL THEN 1 ELSE 0 END)
                AS missing_cost_count,
            SUM(CASE WHEN sold_price_cents IS NULL THEN 1 ELSE 0 END)
                AS missing_price_count
        FROM coins
        WHERE disposition = 'sold'
        """
    ).fetchone()
    proceeds = int(row["proceeds_cents"])
    cost = int(row["cost_basis_cents"])
    return {
        "sold_count": row["sold_count"],
        "proceeds_cents": proceeds,
        "cost_basis_total_cents": cost,
        "realized_pnl_cents": proceeds - cost,
        "missing_cost_count": row["missing_cost_count"] or 0,
        "missing_price_count": row["missing_price_count"] or 0,
    }


def _location_path(loc_map: dict[int, tuple[int | None, str]], location_id: int | None) -> str | None:
    """Replicate Ledger.location_path's ' > '-joined ancestor labels, in Python.

    Walks parent_id up to the root over an in-memory snapshot of the locations
    table. None when the coin has no location.
    """
    if location_id is None:
        return None
    labels: list[str] = []
    current: int | None = location_id
    while current is not None:
        entry = loc_map.get(current)
        if entry is None:  # dangling reference; stop rather than fabricate
            break
        parent_id, label = entry
        labels.append(label)
        current = parent_id
    labels.reverse()
    return " > ".join(labels)


def build_appraisal_report(conn: sqlite3.Connection, top_n: int = 10) -> dict:
    """Whole-portfolio appraisal rollup. Pure read -- writes nothing anywhere."""
    coins = conn.execute(
        """
        SELECT
            c.id AS id,
            c.accession_no AS accession_no,
            c.series AS series,
            c.year AS year,
            c.mintmark AS mintmark,
            c.denomination AS denomination,
            c.country AS country,
            c.grade_bucket AS grade_bucket,
            c.tpg_cert AS tpg_cert,
            c.cost_basis_cents AS cost_basis_cents,
            c.value_est_cents AS value_est_cents,
            c.value_basis AS value_basis,
            c.stale_since AS stale_since,
            c.location_id AS location_id,
            c.composition_id AS composition_id,
            comp.metal AS metal,
            comp.precious_weight_ozt AS ozt
        FROM coins c
        LEFT JOIN compositions comp ON c.composition_id = comp.id
        ORDER BY c.accession_no
        """
    ).fetchall()

    # Snapshot the locations table once for in-Python path reconstruction.
    loc_map = {
        row["id"]: (row["parent_id"], row["label"])
        for row in conn.execute(
            "SELECT id, parent_id, label FROM locations"
        ).fetchall()
    }

    # Rolls (bulk holdings): value non-exhausted rolls that still hold coins.
    # Loaded here so their composition metals join the spot lookup below.
    roll_rows = conn.execute(
        """
        SELECT
            r.roll_no AS roll_no,
            r.denomination AS denomination,
            r.country AS country,
            r.count AS count,
            r.series AS series,
            r.status AS status,
            r.composition_id AS composition_id,
            comp.metal AS metal,
            comp.precious_weight_ozt AS ozt
        FROM rolls r
        LEFT JOIN compositions comp ON r.composition_id = comp.id
        WHERE r.status != 'exhausted' AND r.count > 0
        ORDER BY r.roll_no
        """
    ).fetchall()

    # Spot rows only for metals that actually appear among owned coins (and
    # rolls), and only those with a PRIMARY-source row. Metals present but
    # unpriced are disclosed.
    owned_metals = sorted(
        {row["metal"] for row in coins if row["metal"] is not None}
        | {row["metal"] for row in roll_rows if row["metal"] is not None}
    )
    spot: dict[str, dict] = {}
    spot_cents_by_metal: dict[str, int] = {}
    metals_missing_spot: list[str] = []
    for metal in owned_metals:
        spot_cents = melt.latest_spot_cents(conn, metal, melt.PRIMARY_SOURCE)
        if spot_cents is None:
            metals_missing_spot.append(metal)
            continue
        latest = melt.latest_spot(conn, metal, melt.PRIMARY_SOURCE)
        spot[metal] = {
            "price_usd_cents": latest["price_usd_cents"],
            "fetched_at": latest["fetched_at"],
            "source": latest["source"],
        }
        spot_cents_by_metal[metal] = spot_cents

    # Totals.
    coin_count = len(coins)
    valued_count = 0
    unvalued_count = 0
    best_total = 0
    collectible_total = 0
    melt_total = 0
    face_total = 0
    cost_basis_total = 0
    cost_basis_count = 0
    paired_cost = 0
    paired_best = 0

    # Breakdown: each valued coin lands in exactly one bucket by winning basis.
    bucket = {
        "collectible": {"count": 0, "total_cents": 0},
        "melt": {"count": 0, "total_cents": 0},
        "face": {"count": 0, "total_cents": 0},
    }

    # Data-quality tallies.
    stale_count = 0
    no_composition_count = 0
    basis_unspecified_count = 0

    # Grouping accumulators.
    mint_groups: dict[str, dict] = {}
    series_groups: dict[str, dict] = {}
    metal_groups: dict[str, dict] = {}

    # Per-coin best value keyed by coin id, for the sets rollup and highlights.
    best_by_id: dict[int, int] = {}
    valued_rows: list[dict] = []

    for row in coins:
        # --- melt: composition weight + metal + a primary spot row all required.
        melt_cents: int | None = None
        if row["ozt"] is not None and row["metal"] is not None:
            spot_cents = spot_cents_by_metal.get(row["metal"])
            if spot_cents is not None:
                melt_cents = round(row["ozt"] * spot_cents)

        # --- collectible: numismatic/hybrid estimate; NULL-basis-but-present is
        # still collectible but flagged; 'melt' basis mirrors melt, NOT collectible.
        value_basis = row["value_basis"]
        value_est = row["value_est_cents"]
        collectible_cents: int | None = None
        if value_basis in ("numismatic", "hybrid"):
            collectible_cents = value_est
        elif value_basis is None and value_est is not None:
            collectible_cents = value_est
            basis_unspecified_count += 1

        # --- face.
        face_cents = face_value_cents(row["denomination"], row["country"])

        # --- best: max of the non-None candidates; ties broken by priority
        # collectible (3) > melt (2) > face (1).
        candidates: list[tuple[int, int, str]] = []
        if collectible_cents is not None:
            candidates.append((collectible_cents, 3, "collectible"))
        if melt_cents is not None:
            candidates.append((melt_cents, 2, "melt"))
        if face_cents is not None:
            candidates.append((face_cents, 1, "face"))

        best_cents: int | None = None
        best_basis: str | None = None
        if candidates:
            best_cents, _prio, best_basis = max(candidates, key=lambda t: (t[0], t[1]))

        # Data quality.
        if row["stale_since"] is not None:
            stale_count += 1
        if row["composition_id"] is None:
            no_composition_count += 1

        # Component totals (summed wherever each component is present).
        if collectible_cents is not None:
            collectible_total += collectible_cents
        if melt_cents is not None:
            melt_total += melt_cents
        if face_cents is not None:
            face_total += face_cents

        cost_basis = row["cost_basis_cents"]
        if cost_basis is not None:
            cost_basis_total += cost_basis
            cost_basis_count += 1

        # Grouping keys.
        mint_key = row["mintmark"] if row["mintmark"] is not None else "(none)"
        series_key = row["series"] if row["series"] is not None else "(unattributed)"
        metal_key = row["metal"] if row["metal"] is not None else "base"
        mg = mint_groups.setdefault(mint_key, {"count": 0, "valued_count": 0, "value_cents": 0})
        sg = series_groups.setdefault(series_key, {"count": 0, "valued_count": 0, "value_cents": 0})
        mtg = metal_groups.setdefault(metal_key, {"count": 0, "melt_cents": 0, "value_cents": 0})
        mg["count"] += 1
        sg["count"] += 1
        mtg["count"] += 1
        if melt_cents is not None:
            mtg["melt_cents"] += melt_cents

        if best_cents is None:
            unvalued_count += 1
        else:
            valued_count += 1
            best_total += best_cents
            best_by_id[row["id"]] = best_cents
            bucket[best_basis]["count"] += 1
            bucket[best_basis]["total_cents"] += best_cents
            mg["valued_count"] += 1
            sg["valued_count"] += 1
            mg["value_cents"] += best_cents
            sg["value_cents"] += best_cents
            mtg["value_cents"] += best_cents
            if cost_basis is not None:
                paired_cost += cost_basis
                paired_best += best_cents
            valued_rows.append(
                {
                    "accession_no": row["accession_no"],
                    "series": row["series"],
                    "year": row["year"],
                    "mintmark": row["mintmark"],
                    "denomination": row["denomination"],
                    "grade_bucket": row["grade_bucket"],
                    "tpg_cert": row["tpg_cert"],
                    "best_cents": best_cents,
                    "best_basis": best_basis,
                    "melt_cents": melt_cents,
                    "collectible_cents": collectible_cents,
                    "face_cents": face_cents,
                    "location_path": _location_path(loc_map, row["location_id"]),
                }
            )

    # --- Rolls: value each non-exhausted roll with the shared spot map. A roll
    # with no valuation basis is disclosed by count only (data_quality), never
    # given a made-up figure -- the same NO-FABRICATION rule coins follow.
    from .rolls import roll_valuation  # local import avoids a module import cycle

    roll_count = len(roll_rows)
    roll_face_total = 0
    roll_melt_total = 0
    roll_best_total = 0
    rolls_unvalued_count = 0
    rolls_valued: list[dict] = []
    for r in roll_rows:
        rv = roll_valuation(conn, r, spot_cents_by_metal)
        if rv["face_cents"] is not None:
            roll_face_total += rv["face_cents"]
        if rv["melt_cents"] is not None:
            roll_melt_total += rv["melt_cents"]
        if rv["best_cents"] is None:
            rolls_unvalued_count += 1
            continue
        roll_best_total += rv["best_cents"]
        rolls_valued.append(
            {
                "roll_no": r["roll_no"],
                "denomination": r["denomination"],
                "series": r["series"],
                "count": r["count"],
                "status": r["status"],
                "basis": rv["basis"],
                "value_cents": rv["best_cents"],
            }
        )
    rolls_valued.sort(key=lambda g: (-g["value_cents"], g["roll_no"]))

    # Highlights: top_n by best_cents DESC, tie-break accession_no ASC.
    highlights = sorted(
        valued_rows, key=lambda r: (-r["best_cents"], r["accession_no"])
    )[:top_n]

    # Sets: every set listed; value = sum best over coins assigned to its slots.
    set_rows = conn.execute(
        "SELECT id, set_key, name FROM sets"
    ).fetchall()
    sets_out: list[dict] = []
    for srow in set_rows:
        slots = conn.execute(
            "SELECT coin_id FROM set_slots WHERE set_id = ?", (srow["id"],)
        ).fetchall()
        total_slots = len(slots)
        filled_coin_ids = [s["coin_id"] for s in slots if s["coin_id"] is not None]
        filled = len(filled_coin_ids)
        owned_ids = set(filled_coin_ids)
        value_cents = sum(best_by_id.get(cid, 0) for cid in owned_ids)
        sets_out.append(
            {
                "set_key": srow["set_key"],
                "name": srow["name"],
                "total_slots": total_slots,
                "filled": filled,
                "owned_count": len(owned_ids),
                "value_cents": value_cents,
            }
        )
    sets_out.sort(key=lambda g: (-g["value_cents"], g["set_key"]))

    mints_out = [
        {
            "mintmark": key,
            "count": g["count"],
            "valued_count": g["valued_count"],
            "value_cents": g["value_cents"],
        }
        for key, g in mint_groups.items()
    ]
    mints_out.sort(key=lambda g: (-g["value_cents"], g["mintmark"]))

    series_out = [
        {
            "series": key,
            "count": g["count"],
            "valued_count": g["valued_count"],
            "value_cents": g["value_cents"],
        }
        for key, g in series_groups.items()
    ]
    series_out.sort(key=lambda g: (-g["value_cents"], g["series"]))

    metals_out = [
        {
            "metal": key,
            "count": g["count"],
            "melt_cents": g["melt_cents"],
            "value_cents": g["value_cents"],
        }
        for key, g in metal_groups.items()
    ]
    metals_out.sort(key=lambda g: (-g["value_cents"], g["metal"]))

    return {
        "generated_at": _utcnow(),
        "top_n": top_n,
        "spot": spot,
        "totals": {
            "coin_count": coin_count,
            "valued_count": valued_count,
            "unvalued_count": unvalued_count,
            "best_total_cents": best_total,
            "collectible_total_cents": collectible_total,
            "melt_total_cents": melt_total,
            "face_total_cents": face_total,
            "cost_basis_total_cents": cost_basis_total,
            "cost_basis_count": cost_basis_count,
            "paired_cost_cents": paired_cost,
            "paired_best_cents": paired_best,
            "gain_loss_cents": paired_best - paired_cost,
            "roll_count": roll_count,
            "roll_face_total_cents": roll_face_total,
            "roll_melt_total_cents": roll_melt_total,
            "roll_best_total_cents": roll_best_total,
            "grand_total_cents": best_total + roll_best_total,
        },
        "breakdown": {
            "collectible": bucket["collectible"],
            "melt": bucket["melt"],
            "face": bucket["face"],
            "unvalued": {"count": unvalued_count},
        },
        "highlights": highlights,
        "groups": {
            "sets": sets_out,
            "mints": mints_out,
            "series": series_out,
            "metals": metals_out,
            "rolls": rolls_valued,
        },
        "data_quality": {
            "unvalued_count": unvalued_count,
            "stale_count": stale_count,
            "no_composition_count": no_composition_count,
            "basis_unspecified_count": basis_unspecified_count,
            "metals_missing_spot": metals_missing_spot,
            "rolls_unvalued_count": rolls_unvalued_count,
        },
        "realized": realized_summary(conn),
    }
