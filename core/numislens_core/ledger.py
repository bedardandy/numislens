"""Thin SQLite ledger API for coin collection management."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .db import init_db
from .manifests import load_manifest

GRADE_BUCKETS = frozenset({"AG", "G", "VG", "F", "VF", "XF", "AU", "UNC", "PROOF"})
GRADE_SOURCES = frozenset({"local-vlm", "cross-vote", "cloud", "human", "tpg"})
VALUE_BASES = frozenset({"melt", "numismatic", "hybrid"})
IMAGE_KINDS = frozenset({"obverse", "reverse", "edge", "slab"})


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


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


class Ledger:
    def __init__(self, path) -> None:
        self.conn = init_db(path)
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
    ) -> list[dict]:
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

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        if location_id is not None:
            self._verify_location(location_id)
            loc_filter = "c.location_id IN (SELECT id FROM loc_tree)"
            if where_clause:
                where_clause += f" AND {loc_filter}"
            else:
                where_clause = f"WHERE {loc_filter}"
            sql = f"""
                WITH RECURSIVE loc_tree AS (
                    SELECT id FROM locations WHERE id = ?
                    UNION ALL
                    SELECT l.id FROM locations l
                    INNER JOIN loc_tree lt ON l.parent_id = lt.id
                )
                SELECT c.* FROM coins c
                {where_clause}
                ORDER BY c.accession_no
            """
            rows = self.conn.execute(sql, [location_id, *params]).fetchall()
        else:
            sql = f"""
                SELECT c.* FROM coins c
                {where_clause}
                ORDER BY c.accession_no
            """
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def list_compositions(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, name, metal, fineness, precious_weight_ozt
            FROM compositions
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]

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

            updates = ["last_appraised = ?"]
            update_params: list = [appraised_at]
            if value_cents is not None:
                updates.append("value_est_cents = ?")
                update_params.append(value_cents)
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

    def move_coin(self, accession: str, location_id: int) -> None:
        coin_id = self._coin_id(accession)
        self._verify_location(location_id)
        row = self.conn.execute(
            "SELECT location_id FROM coins WHERE id = ?", (coin_id,)
        ).fetchone()
        from_location = row["location_id"]
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
