"""Thin SQLite ledger API for coin collection management."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .db import connect, init_db
from .manifests import load_manifest

GRADE_BUCKETS = frozenset({"AG", "G", "VG", "F", "VF", "XF", "AU", "UNC", "PROOF"})
GRADE_SOURCES = frozenset({"local-vlm", "cross-vote", "cloud", "human", "tpg"})
VALUE_BASES = frozenset({"melt", "numismatic", "hybrid"})
IMAGE_KINDS = frozenset({"obverse", "reverse", "edge", "slab"})
DISPOSITIONS = frozenset({"owned", "for_sale", "sold", "discarded"})


class LedgerError(Exception):
    pass


class CoinNotFound(LedgerError):
    def __init__(self, accession: str) -> None:
        self.accession = accession
        super().__init__(f"coin not found: {accession}")


class LocationNotFound(LedgerError):
    def __init__(self, location_id: int) -> None:
        self.location_id = location_id
        super().__init__(f"location not found: {location_id}")


class SetNotFound(LedgerError):
    def __init__(self, set_key_or_id: int | str) -> None:
        self.set_key_or_id = set_key_or_id
        super().__init__(f"set not found: {set_key_or_id}")


class SlotError(LedgerError):
    pass


class UnknownSeries(LedgerError):
    """mark_stale(series=...) named a series no coin in the ledger has.

    Carries the list of series that DO exist (capped) so the caller can tell the
    user what is actually markable — fail loud, never silently mark nothing.
    """

    def __init__(self, series: str, known: list[str]) -> None:
        self.series = series
        self.known = known
        shown = ", ".join(known) if known else "(none)"
        super().__init__(
            f"unknown series {series!r}; known series: {shown}"
        )


class MoveConflict(LedgerError):
    def __init__(self, accession: str, expected_from: int | None, actual: int | None) -> None:
        self.accession = accession
        self.expected_from = expected_from
        self.actual = actual
        super().__init__(
            f'move conflict for {accession}: expected location {expected_from}, '
            f'but coin is at {actual}'
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


class Ledger:
    def __init__(self, path, *, migrate: bool = True) -> None:
        # migrate=True runs the (idempotent) migration scan on open. Long-lived
        # callers that have already migrated the database once — the daemon
        # does it at startup in create_app() — pass migrate=False so a fresh
        # connection per request doesn't re-scan migrations every time.
        self.conn = init_db(path) if migrate else connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def _coin_id(self, accession: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM coins WHERE accession_no = ?", (accession,)
        ).fetchone()
        if row is None:
            raise CoinNotFound(accession)
        return row["id"]

    def _set_id(self, set_key_or_id: int | str) -> int:
        if isinstance(set_key_or_id, int):
            row = self.conn.execute(
                "SELECT id FROM sets WHERE id = ?", (set_key_or_id,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id FROM sets WHERE set_key = ?", (set_key_or_id,)
            ).fetchone()
        if row is None:
            raise SetNotFound(set_key_or_id)
        return row["id"]

    def _verify_location(self, location_id: int) -> None:
        row = self.conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise LocationNotFound(location_id)

    def add_coin(
        self,
        *,
        series=None,
        year=None,
        mintmark=None,
        denomination=None,
        country: str = "US",
        composition_id=None,
        weight_g=None,
        diameter_mm=None,
        grade_bucket=None,
        grade_source=None,
        tpg_cert=None,
        cost_basis_cents=None,
        acquired_date=None,
        acquired_source=None,
        value_est_cents=None,
        value_basis=None,
        appraisal_confidence=None,
        location_id=None,
        notes=None,
    ) -> str:
        if grade_bucket is not None and grade_bucket not in GRADE_BUCKETS:
            raise ValueError(f"invalid grade_bucket: {grade_bucket!r}")
        if grade_source is not None and grade_source not in GRADE_SOURCES:
            raise ValueError(f"invalid grade_source: {grade_source!r}")
        if value_basis is not None and value_basis not in VALUE_BASES:
            raise ValueError(f"invalid value_basis: {value_basis!r}")
        if cost_basis_cents is not None and not isinstance(cost_basis_cents, int):
            raise ValueError("cost_basis_cents must be an int")
        if value_est_cents is not None and not isinstance(value_est_cents, int):
            raise ValueError("value_est_cents must be an int")
        if composition_id is not None:
            row = self.conn.execute(
                "SELECT id FROM compositions WHERE id = ?", (composition_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown composition_id: {composition_id}")
        if location_id is not None:
            self._verify_location(location_id)

        now = _utcnow()
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                """
                SELECT 1 + COALESCE(MAX(CAST(substr(accession_no, 4) AS INTEGER)), 0)
                FROM coins
                """
            ).fetchone()
            n = row[0]
            accession = "NL-%06d" % n
            cur = self.conn.execute(
                """
                INSERT INTO coins (
                    accession_no, series, year, mintmark, denomination, country,
                    composition_id, weight_g, diameter_mm, grade_bucket, grade_source,
                    tpg_cert, cost_basis_cents, acquired_date, acquired_source,
                    value_est_cents, value_basis, appraisal_confidence,
                    location_id, notes, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    accession,
                    series,
                    year,
                    mintmark,
                    denomination,
                    country,
                    composition_id,
                    weight_g,
                    diameter_mm,
                    grade_bucket,
                    grade_source,
                    tpg_cert,
                    cost_basis_cents,
                    acquired_date,
                    acquired_source,
                    value_est_cents,
                    value_basis,
                    appraisal_confidence,
                    location_id,
                    notes,
                    now,
                ),
            )
            coin_id = cur.lastrowid
            self.conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (?, 'added', ?, ?)
                """,
                (coin_id, now, json.dumps(location_id)),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return accession

    def get_coin(self, accession: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM coins WHERE accession_no = ?", (accession,)
        ).fetchone()
        return _row_to_dict(row)

    def _filter_conditions(
        self,
        *,
        series=None,
        year=None,
        mintmark=None,
        denomination=None,
        grade_bucket=None,
        composition_id=None,
        disposition=None,
    ) -> tuple[list[str], list]:
        """Shared WHERE builder for find_coins/count_coins."""
        conditions: list[str] = []
        params: list = []
        if series is not None:
            conditions.append("c.series = ?")
            params.append(series)
        if year is not None:
            conditions.append("c.year = ?")
            params.append(year)
        if mintmark is not None:
            conditions.append("c.mintmark = ?")
            params.append(mintmark)
        if denomination is not None:
            conditions.append("c.denomination = ?")
            params.append(denomination)
        if grade_bucket is not None:
            conditions.append("c.grade_bucket = ?")
            params.append(grade_bucket)
        if composition_id is not None:
            conditions.append("c.composition_id = ?")
            params.append(composition_id)
        if disposition is not None:
            if disposition not in DISPOSITIONS:
                raise ValueError(f"invalid disposition: {disposition!r}")
            conditions.append("c.disposition = ?")
            params.append(disposition)
        return conditions, params

    @staticmethod
    def _check_paging(limit: int | None, offset: int) -> None:
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")

    def find_coins(
        self,
        *,
        series=None,
        year=None,
        mintmark=None,
        denomination=None,
        grade_bucket=None,
        composition_id=None,
        location_id=None,
        disposition=None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        self._check_paging(limit, offset)
        conditions, params = self._filter_conditions(
            series=series,
            year=year,
            mintmark=mintmark,
            denomination=denomination,
            grade_bucket=grade_bucket,
            composition_id=composition_id,
            disposition=disposition,
        )

        if location_id is not None:
            self._verify_location(location_id)
            all_conds = ["c.location_id IN (SELECT id FROM loc_tree)", *conditions]
            sql = f"""
                WITH RECURSIVE loc_tree AS (
                    SELECT id FROM locations WHERE id = ?
                    UNION ALL
                    SELECT l.id FROM locations l
                    INNER JOIN loc_tree lt ON l.parent_id = lt.id
                )
                SELECT c.* FROM coins c
                WHERE {" AND ".join(all_conds)}
                ORDER BY c.accession_no
            """
            query_params: list = [location_id, *params]
        else:
            where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            sql = f"SELECT c.* FROM coins c{where_clause} ORDER BY c.accession_no"
            query_params = list(params)

        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            query_params += [limit, offset]
        elif offset:
            # LIMIT -1 means unlimited in SQLite; still honor a bare offset.
            sql += " LIMIT -1 OFFSET ?"
            query_params.append(offset)

        return [dict(row) for row in self.conn.execute(sql, query_params)]

    def count_coins(self, *, location_id: int | None = None, **filters) -> int:
        """Total coins matching the same filters as find_coins (no paging)."""
        self._check_paging(None, 0)
        conditions, params = self._filter_conditions(**filters)
        if location_id is not None:
            self._verify_location(location_id)
            all_conds = ["c.location_id IN (SELECT id FROM loc_tree)", *conditions]
            sql = f"""
                WITH RECURSIVE loc_tree AS (
                    SELECT id FROM locations WHERE id = ?
                    UNION ALL
                    SELECT l.id FROM locations l
                    INNER JOIN loc_tree lt ON l.parent_id = lt.id
                )
                SELECT COUNT(*) FROM coins c
                WHERE {" AND ".join(all_conds)}
            """
            row = self.conn.execute(sql, [location_id, *params]).fetchone()
        else:
            where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            row = self.conn.execute(
                f"SELECT COUNT(*) FROM coins c{where_clause}", params
            ).fetchone()
        return row[0]

    def find_duplicates(self) -> list[dict]:
        """Candidate duplicate identities: same series+year+mintmark.

        A blank mintmark groups with itself (two unmarked 1922 Peace dollars
        are exactly the double-entry an inheritor needs to catch). Read-only —
        adjudication is human work; this only surfaces the suspects with their
        locations.
        """
        groups = self.conn.execute(
            """
            SELECT series, year, mintmark, COUNT(*) AS n
            FROM coins
            WHERE series IS NOT NULL AND year IS NOT NULL
            GROUP BY series, year, mintmark
            HAVING n > 1
            ORDER BY n DESC, series, year, mintmark
            """
        ).fetchall()
        out: list[dict] = []
        for g in groups:
            members = self.conn.execute(
                """
                SELECT accession_no, location_id FROM coins
                WHERE series = ? AND year = ? AND mintmark IS ?
                ORDER BY accession_no
                """,
                (g["series"], g["year"], g["mintmark"]),
            ).fetchall()
            out.append(
                {
                    "series": g["series"],
                    "year": g["year"],
                    "mintmark": g["mintmark"],
                    "count": g["n"],
                    "coins": [
                        {
                            "accession_no": m["accession_no"],
                            "location_path": (
                                self.location_path(m["location_id"])
                                if m["location_id"] is not None
                                else None
                            ),
                        }
                        for m in members
                    ],
                }
            )
        return out

    def list_compositions(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, name, metal, fineness, precious_weight_ozt
            FROM compositions
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    # Human correction fields for edit_coin. Deliberately EXCLUDES
    # grade_bucket/grade_source: grade changes flow through record_appraisal
    # or the vision writeback so provenance stays append-only (AGENTS.md
    # invariant 2). A present-but-None value CLEARS the field — an explicit
    # human correction, event-logged like every other edit.
    EDITABLE_FIELDS = (
        "series",
        "year",
        "mintmark",
        "denomination",
        "country",
        "composition_id",
        "weight_g",
        "diameter_mm",
        "tpg_cert",
        "cost_basis_cents",
        "acquired_date",
        "acquired_source",
        "value_est_cents",
        "value_basis",
        "appraisal_confidence",
        "location_id",
        "notes",
    )

    def edit_coin(self, accession: str, **fields) -> dict:
        """Apply a human correction to an existing coin; log before/after.

        Only EDITABLE_FIELDS may be named; anything else raises ValueError.
        Passing None for a field clears it. Returns ``{"changed": {field:
        [before, after]}, "coin": <fresh row>}`` and appends an ``edited``
        event whose detail records exactly what changed (the audit trail IS
        the history — no field is silently overwritten).
        """
        coin_id = self._coin_id(accession)
        unknown = set(fields) - set(self.EDITABLE_FIELDS)
        if unknown:
            raise ValueError(
                f"not editable fields: {sorted(unknown)} "
                "(grade changes go through appraisals)"
            )
        if not fields:
            raise ValueError("edit_coin requires at least one field")

        if "value_basis" in fields and fields["value_basis"] is not None:
            if fields["value_basis"] not in VALUE_BASES:
                raise ValueError(f"invalid value_basis: {fields['value_basis']!r}")
        for money_field in ("cost_basis_cents", "value_est_cents"):
            if (
                money_field in fields
                and fields[money_field] is not None
                and not isinstance(fields[money_field], int)
            ):
                raise ValueError(f"{money_field} must be an int")
        if "composition_id" in fields and fields["composition_id"] is not None:
            row = self.conn.execute(
                "SELECT id FROM compositions WHERE id = ?",
                (fields["composition_id"],),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown composition_id: {fields['composition_id']}")
        if "location_id" in fields and fields["location_id"] is not None:
            self._verify_location(fields["location_id"])

        current = self.conn.execute(
            "SELECT * FROM coins WHERE id = ?", (coin_id,)
        ).fetchone()
        changed: dict[str, list] = {}
        for key, new_value in fields.items():
            old_value = current[key]
            if old_value != new_value:
                changed[key] = [old_value, new_value]

        result: dict = {"changed": changed}
        if not changed:
            return result

        now = _utcnow()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = [*fields.values(), coin_id]
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(f"UPDATE coins SET {set_clause} WHERE id = ?", params)
            self.conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (?, 'edited', ?, ?)
                """,
                (coin_id, now, json.dumps({"changed": changed})),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        result["coin"] = self.get_coin(accession)
        return result

    def create_location(self, kind: str, label: str, parent: int | None = None) -> int:
        if parent is not None:
            self._verify_location(parent)
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            cur = self.conn.execute(
                "INSERT INTO locations (parent_id, kind, label) VALUES (?, ?, ?)",
                (parent, kind, label),
            )
            location_id = cur.lastrowid
        return location_id

    def location_path(self, location_id: int) -> str:
        self._verify_location(location_id)
        labels: list[str] = []
        current_id: int | None = location_id
        while current_id is not None:
            row = self.conn.execute(
                "SELECT id, parent_id, label FROM locations WHERE id = ?",
                (current_id,),
            ).fetchone()
            if row is None:
                raise LocationNotFound(location_id)
            labels.append(row["label"])
            current_id = row["parent_id"]
        labels.reverse()
        return " > ".join(labels)

    def contents(self, location_id: int, recursive: bool = True) -> list[dict]:
        self._verify_location(location_id)
        if recursive:
            sql = """
                WITH RECURSIVE loc_tree AS (
                    SELECT id FROM locations WHERE id = ?
                    UNION ALL
                    SELECT l.id FROM locations l
                    INNER JOIN loc_tree lt ON l.parent_id = lt.id
                )
                SELECT c.* FROM coins c
                WHERE c.location_id IN (SELECT id FROM loc_tree)
                ORDER BY c.accession_no
            """
            rows = self.conn.execute(sql, (location_id,)).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT c.* FROM coins c
                WHERE c.location_id = ?
                ORDER BY c.accession_no
                """,
                (location_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def load_set_manifest(self, path) -> int:
        manifest = load_manifest(path)
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute(
                """
                INSERT INTO sets (set_key, name, series, composition_ref)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(set_key) DO UPDATE SET
                    name = excluded.name,
                    series = excluded.series,
                    composition_ref = excluded.composition_ref
                """,
                (
                    manifest["id"],
                    manifest["name"],
                    manifest.get("series"),
                    manifest["composition_ref"],
                ),
            )
            row = self.conn.execute(
                "SELECT id FROM sets WHERE set_key = ?", (manifest["id"],)
            ).fetchone()
            set_id = row["id"]
            for slot in manifest["slots"]:
                note = slot.get("note", "")
                key_date = 1 if slot.get("key_date") else 0
                self.conn.execute(
                    """
                    INSERT INTO set_slots (set_id, year, mint, note, key_date)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(set_id, year, mint, note) DO UPDATE SET
                        key_date = excluded.key_date
                    """,
                    (set_id, slot["year"], slot["mint"], note, key_date),
                )
        return set_id

    def assign_to_slot(self, set_id, slot: dict, accession: str) -> None:
        resolved_set_id = self._set_id(set_id)
        year = slot["year"]
        mint = slot["mint"]
        note = slot.get("note", "")
        row = self.conn.execute(
            """
            SELECT id, coin_id FROM set_slots
            WHERE set_id = ? AND year = ? AND mint = ? AND note = ?
            """,
            (resolved_set_id, year, mint, note),
        ).fetchone()
        if row is None:
            raise SlotError(
                f"no slot for set {set_id!r}: year={year}, mint={mint!r}, note={note!r}"
            )
        if row["coin_id"] is not None:
            raise SlotError(
                f"slot already filled (year={year}, mint={mint!r}, note={note!r})"
            )
        coin_id = self._coin_id(accession)
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute(
                "UPDATE set_slots SET coin_id = ? WHERE id = ?", (coin_id, row["id"])
            )

    def set_gaps(self, set_id) -> list[dict]:
        resolved_set_id = self._set_id(set_id)
        rows = self.conn.execute(
            """
            SELECT year, mint, note, key_date FROM set_slots
            WHERE set_id = ? AND coin_id IS NULL
            ORDER BY year, mint
            """,
            (resolved_set_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_completion(self, set_id) -> tuple[int, int]:
        resolved_set_id = self._set_id(set_id)
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN coin_id IS NOT NULL THEN 1 ELSE 0 END) AS filled
            FROM set_slots WHERE set_id = ?
            """,
            (resolved_set_id,),
        ).fetchone()
        return (row["filled"] or 0, row["total"])

    def set_board(self, set_id) -> dict:
        resolved_set_id = self._set_id(set_id)
        meta = self.conn.execute(
            'SELECT set_key, name, series, composition_ref FROM sets WHERE id = ?',
            (resolved_set_id,),
        ).fetchone()
        filled, total = self.set_completion(resolved_set_id)
        rows = self.conn.execute(
            '''
            SELECT s.year, s.mint, s.note, s.key_date,
                   c.accession_no AS accession, c.grade_bucket AS grade_bucket
            FROM set_slots s
            LEFT JOIN coins c ON s.coin_id = c.id
            WHERE s.set_id = ?
            ORDER BY s.year, s.mint, s.note
            ''',
            (resolved_set_id,),
        ).fetchall()
        slots = [dict(row) for row in rows]
        return {
            'set_key': meta['set_key'],
            'name': meta['name'],
            'series': meta['series'],
            'composition_ref': meta['composition_ref'],
            'filled': filled,
            'total': total,
            'slots': slots,
        }

    def record_appraisal(
        self,
        accession: str,
        appraised_by: str,
        *,
        grade_bucket=None,
        value_cents=None,
        value_basis=None,
        rationale=None,
        token_cost=None,
        confidence=None,
        appraised_at=None,
    ) -> int:
        coin_id = self._coin_id(accession)
        if grade_bucket is not None and grade_bucket not in GRADE_BUCKETS:
            raise ValueError(f"invalid grade_bucket: {grade_bucket!r}")
        if value_basis is not None and value_basis not in VALUE_BASES:
            raise ValueError(f"invalid value_basis: {value_basis!r}")
        if appraised_at is None:
            appraised_at = _utcnow()

        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            cur = self.conn.execute(
                """
                INSERT INTO appraisals (
                    coin_id, appraised_by, appraised_at, grade_bucket,
                    value_cents, value_basis, rationale, token_cost, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    coin_id,
                    appraised_by,
                    appraised_at,
                    grade_bucket,
                    value_cents,
                    value_basis,
                    rationale,
                    token_cost,
                    confidence,
                ),
            )
            appraisal_id = cur.lastrowid

            # Recording an appraisal CLEARS staleness — this is the one, atomic
            # place value-watch staleness is retired (same transaction as the
            # appraisal insert). A fresh appraisal is exactly the signal the
            # stale flag was asking for.
            updates = ["last_appraised = ?", "stale_since = NULL", "stale_reason = NULL"]
            update_params: list = [appraised_at]
            if value_cents is not None:
                updates.append("value_est_cents = ?")
                update_params.append(value_cents)
                # A valued appraisal moves a melt-basis coin OFF melt (the docs'
                # stated behavior, previously unenforced): otherwise the daily
                # melt recompute would silently stomp the human's value back to
                # spot. 'hybrid' keeps the melt floor visible via the daily run
                # while the human estimate becomes the headline number.
                if value_basis is None:
                    row = self.conn.execute(
                        "SELECT value_basis FROM coins WHERE id = ?", (coin_id,)
                    ).fetchone()
                    if row["value_basis"] == "melt":
                        updates.append("value_basis = 'hybrid'")
            if value_basis is not None:
                updates.append("value_basis = ?")
                update_params.append(value_basis)
            if confidence is not None:
                updates.append("appraisal_confidence = ?")
                update_params.append(confidence)
            update_params.append(coin_id)
            self.conn.execute(
                f"UPDATE coins SET {', '.join(updates)} WHERE id = ?",
                update_params,
            )
            self.conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (?, 'appraised', ?, ?)
                """,
                (coin_id, appraised_at, json.dumps({"appraisal_id": appraisal_id})),
            )
        return appraisal_id

    # Identification fields the vision writeback may fill. country carries a
    # DEFAULT 'US', so it is effectively never null and will always be reported
    # skipped — that is fine, it is included for completeness.
    IDENTIFICATION_FIELDS = (
        "series",
        "year",
        "mintmark",
        "denomination",
        "country",
        "composition_id",
        "grade_bucket",
        "grade_source",
    )

    def update_identification(self, accession: str, **fields) -> dict:
        """Fill NULL identification fields only; never overwrite existing data.

        The single append-write path the Phase-4 vision writeback uses to record
        a gated identification onto an existing coin. Each provided, non-None
        field is written ONLY if the coin's current value is NULL; a field that
        already has a value is left untouched and reported in ``skipped`` (never
        overwrite a user/human-entered identity or grade). ``grade_bucket`` here
        is legitimate per the "grade only from a photo pipeline or human/TPG"
        rule — the pipeline IS that source, tagged via ``grade_source``.

        Returns ``{"written": {...}, "skipped": {...current values...}}`` and
        appends an ``identified`` event listing what was written.
        """
        coin_id = self._coin_id(accession)
        unknown = set(fields) - set(self.IDENTIFICATION_FIELDS)
        if unknown:
            raise ValueError(f"not identification fields: {sorted(unknown)}")
        provided = {k: v for k, v in fields.items() if v is not None}
        if "grade_bucket" in provided and provided["grade_bucket"] not in GRADE_BUCKETS:
            raise ValueError(f"invalid grade_bucket: {provided['grade_bucket']!r}")
        if "grade_source" in provided and provided["grade_source"] not in GRADE_SOURCES:
            raise ValueError(f"invalid grade_source: {provided['grade_source']!r}")
        if "composition_id" in provided:
            row = self.conn.execute(
                "SELECT id FROM compositions WHERE id = ?", (provided["composition_id"],)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown composition_id: {provided['composition_id']}")

        current = self.conn.execute(
            "SELECT * FROM coins WHERE id = ?", (coin_id,)
        ).fetchone()
        written: dict = {}
        skipped: dict = {}
        for key, value in provided.items():
            if current[key] is None:
                written[key] = value
            else:
                skipped[key] = current[key]

        if written:
            now = _utcnow()
            set_clause = ", ".join(f"{k} = ?" for k in written)
            params = [*written.values(), coin_id]
            with self.conn:
                self.conn.execute("PRAGMA foreign_keys = ON")
                self.conn.execute(
                    f"UPDATE coins SET {set_clause} WHERE id = ?", params
                )
                self.conn.execute(
                    """
                    INSERT INTO events (coin_id, event_type, at, detail)
                    VALUES (?, 'identified', ?, ?)
                    """,
                    (coin_id, now, json.dumps(written)),
                )
        return {"written": written, "skipped": skipped}

    def list_appraisals(self, accession: str) -> list[dict]:
        """All appraisal rows for a coin, newest first (append-only read).

        Exposed so the vision worker can tell whether a coin already has a
        ``vision:*`` appraisal and skip re-processing it under ``--pending``.
        """
        coin_id = self._coin_id(accession)
        rows = self.conn.execute(
            """
            SELECT * FROM appraisals
            WHERE coin_id = ?
            ORDER BY appraised_at DESC, id DESC
            """,
            (coin_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_appraisal(self, accession: str) -> dict | None:
        coin_id = self._coin_id(accession)
        row = self.conn.execute(
            """
            SELECT * FROM appraisals
            WHERE coin_id = ?
            ORDER BY appraised_at DESC, id DESC
            LIMIT 1
            """,
            (coin_id,),
        ).fetchone()
        return _row_to_dict(row)

    # ------------------------------------------------------------------
    # Value-watch staleness (Phase 6)
    #
    # Staleness is METADATA, never a value. Marking a coin stale flags that a
    # market signal (weekly digest hit, or a >=10% spot move) suggests its
    # numismatic premium may have drifted and a lazy re-appraisal is warranted.
    # It NEVER changes value_est_cents. record_appraisal is the only clear path.
    # ------------------------------------------------------------------

    def known_series(self) -> list[str]:
        """DISTINCT non-null series present on coins, ordered — the markable set.

        This is the universe ``mark_stale(series=...)`` validates against and the
        list surfaced (capped) when an unknown series is named.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT series FROM coins WHERE series IS NOT NULL ORDER BY series"
        ).fetchall()
        return [row["series"] for row in rows]

    def _mark_coin_ids_stale(self, coin_ids: list[int], reason: str, now: str) -> int:
        if not coin_ids:
            return 0
        placeholders = ",".join("?" for _ in coin_ids)
        cur = self.conn.execute(
            f"UPDATE coins SET stale_since = ?, stale_reason = ? WHERE id IN ({placeholders})",
            [now, reason, *coin_ids],
        )
        return cur.rowcount

    def mark_stale(
        self,
        *,
        accessions: list[str] | None = None,
        series: str | None = None,
        set_id: int | str | None = None,
        reason: str,
    ) -> int:
        """Flag coins stale for value-watch. Returns the number of coins marked.

        Provide EXACTLY ONE target:

        - ``accessions``: an explicit list; an unknown accession raises
          ``CoinNotFound`` (fail loud — nothing is marked).
        - ``series``: case-insensitive EXACT match against the DISTINCT series
          stored on coins. An unknown series raises ``UnknownSeries`` carrying
          the list of series that DO exist (capped at 50).
        - ``set_id``: numeric id or set_key; marks every coin assigned to a slot
          of that set.

        ``reason`` is required and stored verbatim in ``stale_reason``. Marking
        refreshes ``stale_since`` to now and overwrites any prior reason. This
        never touches ``value_est_cents``.
        """
        if not reason:
            raise ValueError("mark_stale requires a non-empty reason")
        targets = [t for t in (accessions, series, set_id) if t is not None]
        if len(targets) != 1:
            raise ValueError(
                "mark_stale requires exactly one of accessions, series, or set_id"
            )

        now = _utcnow()

        if accessions is not None:
            # Resolve every accession first so an unknown one fails loud before
            # anything is marked.
            coin_ids = [self._coin_id(acc) for acc in accessions]
        elif series is not None:
            known = self.known_series()
            match = {s.lower(): s for s in known}.get(series.lower())
            if match is None:
                raise UnknownSeries(series, known[:50])
            coin_ids = [
                row["id"]
                for row in self.conn.execute(
                    "SELECT id FROM coins WHERE series = ?", (match,)
                ).fetchall()
            ]
        else:
            resolved_set_id = self._set_id(set_id)
            coin_ids = [
                row["coin_id"]
                for row in self.conn.execute(
                    "SELECT coin_id FROM set_slots WHERE set_id = ? AND coin_id IS NOT NULL",
                    (resolved_set_id,),
                ).fetchall()
            ]

        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            return self._mark_coin_ids_stale(coin_ids, reason, now)

    def list_stale(self) -> list[dict]:
        """All currently-stale coins (full rows), newest staleness first."""
        rows = self.conn.execute(
            """
            SELECT * FROM coins
            WHERE stale_since IS NOT NULL
            ORDER BY stale_since DESC, accession_no
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def watchlist(self, n: int = 25) -> list[dict]:
        """Top-``n`` coins by value_est_cents (ties by accession).

        Coins with a NULL value are EXCLUDED — an unappraised coin is not
        watchable, it is simply unpriced. This is the monthly per-coin sweep
        candidate set.
        """
        if n < 0:
            raise ValueError("watchlist n must be non-negative")
        rows = self.conn.execute(
            """
            SELECT * FROM coins
            WHERE value_est_cents IS NOT NULL
            ORDER BY value_est_cents DESC, accession_no
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_image(
        self,
        accession: str,
        kind: str,
        content_hash: str,
        path: str,
    ) -> dict:
        """Record a coin image row (idempotent on content_hash per coin).

        Returns the coin_images row as a dict. If a row with the same
        (coin_id, content_hash) already exists it is returned unchanged and no
        new row is inserted (content-hash dedup); the caller can detect this by
        comparing the returned kind/path to what it passed in.
        """
        if kind not in IMAGE_KINDS:
            raise ValueError(f"invalid image kind: {kind!r}")
        if not content_hash:
            raise ValueError("content_hash must be non-empty")
        coin_id = self._coin_id(accession)
        existing = self.conn.execute(
            """
            SELECT * FROM coin_images
            WHERE coin_id = ? AND content_hash = ?
            ORDER BY id LIMIT 1
            """,
            (coin_id, content_hash),
        ).fetchone()
        if existing is not None:
            return dict(existing)
        now = _utcnow()
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            cur = self.conn.execute(
                """
                INSERT INTO coin_images (coin_id, kind, content_hash, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (coin_id, kind, content_hash, path, now),
            )
            image_id = cur.lastrowid
        row = self.conn.execute(
            "SELECT * FROM coin_images WHERE id = ?", (image_id,)
        ).fetchone()
        return dict(row)

    def list_images(self, accession: str) -> list[dict]:
        coin_id = self._coin_id(accession)
        rows = self.conn.execute(
            "SELECT * FROM coin_images WHERE coin_id = ? ORDER BY id",
            (coin_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def move_coin(self, accession: str, location_id: int, expected_from: int | None = None) -> None:
        coin_id = self._coin_id(accession)
        self._verify_location(location_id)
        row = self.conn.execute(
            "SELECT location_id FROM coins WHERE id = ?", (coin_id,)
        ).fetchone()
        from_location = row["location_id"]
        if expected_from is not None and from_location != expected_from:
            raise MoveConflict(accession, expected_from, from_location)
        now = _utcnow()
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute(
                "UPDATE coins SET location_id = ? WHERE id = ?",
                (location_id, coin_id),
            )
            self.conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (?, 'moved', ?, ?)
                """,
                (
                    coin_id,
                    now,
                    json.dumps({"from": from_location, "to": location_id}),
                ),
            )

    def set_disposition(
        self,
        accession: str,
        disposition: str,
        *,
        sold_date: str | None = None,
        sold_price_cents: int | None = None,
        sold_venue: str | None = None,
    ) -> dict:
        """Move a coin through the owned -> for_sale -> sold lifecycle.

        ``disposition`` is one of ``owned | for_sale | sold | discarded``.
        Marking 'sold' REQUIRES an explicit ``sold_price_cents`` (0 is valid —
        a giveaway is a real outcome, not a missing fact); date and venue are
        optional because they are often genuinely unknown. Any non-sold state
        clears the sold_* fields (a correction moves the facts with it). Every
        transition appends a 'disposition' event; rows are never deleted.

        Returns the fresh coin row.
        """
        if disposition not in DISPOSITIONS:
            raise ValueError(f"invalid disposition: {disposition!r}")
        coin_id = self._coin_id(accession)
        if disposition == "sold":
            if sold_price_cents is None:
                raise ValueError(
                    "marking sold requires sold_price_cents "
                    "(use 0 for a giveaway — never leave it unknown)"
                )
            if not isinstance(sold_price_cents, int):
                raise ValueError("sold_price_cents must be an int")
        else:
            sold_date = sold_price_cents = sold_venue = None

        current = self.conn.execute(
            "SELECT disposition FROM coins WHERE id = ?", (coin_id,)
        ).fetchone()
        previous = current["disposition"]
        now = _utcnow()

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                """
                UPDATE coins
                SET disposition = ?, sold_date = ?, sold_price_cents = ?, sold_venue = ?
                WHERE id = ?
                """,
                (disposition, sold_date, sold_price_cents, sold_venue, coin_id),
            )
            detail: dict = {"from": previous, "to": disposition}
            if disposition == "sold":
                detail["sold"] = {
                    "date": sold_date,
                    "price_cents": sold_price_cents,
                    "venue": sold_venue,
                }
            self.conn.execute(
                """
                INSERT INTO events (coin_id, event_type, at, detail)
                VALUES (?, 'disposition', ?, ?)
                """,
                (coin_id, now, json.dumps(detail)),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.get_coin(accession)
