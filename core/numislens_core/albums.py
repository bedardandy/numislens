"""Album / coin-folder photo import: parsing, matching, and commit.

A pure connection-based module in the shape of :mod:`rolls` and :mod:`report`
-- it does NOT extend the Ledger class. It covers the four pieces of album-import
logic that must be unit-testable without a web server:

1. ``parse_slot_label`` / ``extract_century_hint`` -- turn the printed text under
   a folder hole ("1943 D", "1909 S V.D.B.") into a (year, mint, note) triple,
   with the strict NO-FABRICATION rule that a year is NEVER invented (a bare
   two-digit "'43" resolves only with a century hint from the page title).
2. ``merge_page_slots`` -- collapse the slot readings of every page of an import
   into one logical slot list, deduped by (year, mint, note). Conflicting
   fill-states collapse to 'uncertain' (never a guess).
3. ``match_manifests`` -- suggest which shipped set a photo set covers, by
   (year, mint) containment. Suggest-only: threshold judgements are the human's.
4. ``commit_import`` -- turn a reviewed import into a real set + coin rows, with
   uncertain slots gated (block or treat-as-empty; NEVER filled).

Plus ``needs`` -- what a set is still missing, built on the set_slots table.

Album-level mutations are append-logged to the append-only ``events`` table with
``coin_id`` NULL and an ``event_type`` like ``album:committed``; the ``detail``
JSON always carries the ``import_id``. Coin rows created on commit get their own
``added`` events (coin_id set), exactly like ``Ledger.add_coin``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .ledger import SetNotFound
from .manifests import ManifestError, load_manifest, validate_manifest

# core/sets/*.json -- the shipped set manifests (this file lives in
# core/numislens_core/, so the sets dir is a sibling of the package).
_SETS_DIR = Path(__file__).resolve().parent.parent / "sets"

# Mint alphabet, identical to manifests.ALLOWED_MINTS and canon.MINTMARKS.
ALLOWED_MINTS = frozenset({"P", "D", "S", "O", "CC", "W"})

# Canonical denomination implied by a resolved series. Deliberately duplicated
# (small, stable) from daemon quickadd._SERIES_DENOMINATION: core must not import
# the daemon. Unknown series -> None (denomination left NULL, never guessed).
_SERIES_DENOMINATION = {
    "Morgan Dollar": "dollar",
    "Peace Dollar": "dollar",
    "Washington Quarter": "quarter",
    "Lincoln Wheat Cent": "cent",
    "Lincoln Cent": "cent",
}

_YEAR4_RE = re.compile(r"^(1[5-9]\d\d|20\d\d)$")
_YEAR2_RE = re.compile(r"^'?(\d{2})$")
_YEAR_ANY_RE = re.compile(r"(1[5-9]\d\d|20\d\d)")


class AlbumError(Exception):
    """A bad album operation (validation, missing manifest, etc.)."""


class AlbumNotFound(AlbumError):
    def __init__(self, import_id: int) -> None:
        self.import_id = import_id
        super().__init__(f"album import not found: {import_id}")


class AlbumUncertain(AlbumError):
    """Commit was blocked because uncertain slots remain (policy='block').

    Carries the count so the API layer can 409 with a helpful message. Uncertain
    is a first-class state: the commit refuses to guess it filled OR empty unless
    the caller explicitly opts into a policy.
    """

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"{count} slot(s) are uncertain; resolve them or pass "
            "uncertain_policy='empty' to treat them as missing"
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Label parsing (pure)
# ---------------------------------------------------------------------------

def _canon_mint(token: str) -> str | None:
    """A token is a mintmark only if it is in the allowed alphabet.

    Periods are stripped ("S." -> "S") and case is ignored; anything else -> None
    (it is note text, not a mint).
    """
    t = token.replace(".", "").strip().upper()
    return t if t in ALLOWED_MINTS else None


def _canon_note(tokens: list[str]) -> str:
    """Join leftover label tokens into a note, stripping periods ("V.D.B."->VDB)."""
    note = " ".join(tokens).replace(".", "")
    return re.sub(r"\s+", " ", note).strip()


def parse_slot_label(
    text: str, century_hint: int | None = None
) -> tuple[int | None, str | None, str]:
    """Parse a folder-hole label into ``(year, mint, note)``.

    Rules (NO-FABRICATION -- a year is never invented):

    - ``"1943 D"``            -> ``(1943, 'D', '')``
    - bare year ``"1916"``    -> ``(1916, 'P', '')``  (folders omit the P mark)
    - ``"1909 S V.D.B."``     -> ``(1909, 'S', 'VDB')``
    - ``"1885-CC"``           -> ``(1885, 'CC', '')`` (hyphen year-mint form)
    - two-digit ``"'43"`` / ``"43 D"`` resolve ONLY with a ``century_hint``
      (e.g. 1900 from a "1941-1958" page title); without one -> unparseable.
    - anything with no resolvable year -> ``(None, None, <original text>)``.

    Mint tokens are limited to the schema enum P/D/S/O/CC/W (case-insensitive,
    periods stripped). A parsed label with no explicit mint defaults to 'P'.
    """
    original = text if isinstance(text, str) else ""
    if not isinstance(text, str) or not text.strip():
        return (None, None, original)

    # Split on whitespace AND hyphens so "1885-CC" / "1909-S" tokenize cleanly.
    tokens = [t for t in re.split(r"[\s\-]+", text.strip()) if t]

    # Find a 4-digit year first (the common, unambiguous case).
    year: int | None = None
    year_idx: int | None = None
    for i, tok in enumerate(tokens):
        if _YEAR4_RE.match(tok.strip(".,;:")):
            year = int(tok.strip(".,;:"))
            year_idx = i
            break

    # Fall back to a two-digit year, resolvable only with a century hint.
    if year is None:
        for i, tok in enumerate(tokens):
            m = _YEAR2_RE.match(tok.strip(".,;:"))
            if m:
                if century_hint is None:
                    # Cannot resolve the century -> refuse to invent one.
                    return (None, None, original)
                year = century_hint + int(m.group(1))
                year_idx = i
                break

    if year is None or year_idx is None:
        return (None, None, original)

    rest = tokens[:year_idx] + tokens[year_idx + 1:]
    mint: str | None = None
    note_tokens: list[str] = []
    for tok in rest:
        canon = _canon_mint(tok)
        if canon is not None and mint is None:
            mint = canon
        else:
            note_tokens.append(tok)
    if mint is None:
        mint = "P"  # a parsed year with no printed mark is Philadelphia
    return (year, mint, _canon_note(note_tokens))


def extract_century_hint(page_title: str) -> int | None:
    """Return the century floor (e.g. 1900) of the first year in a page title.

    "LINCOLN CENTS 1941-1958" -> 1900. None when no 4-digit year is present.
    Used to resolve two-digit slot labels on that page.
    """
    if not page_title:
        return None
    m = _YEAR_ANY_RE.search(page_title)
    if m is None:
        return None
    return (int(m.group(1)) // 100) * 100


# ---------------------------------------------------------------------------
# 2. Merge page slots (conn read)
# ---------------------------------------------------------------------------

def _merge_fill(states: list[str]) -> str:
    """Collapse duplicate slot fill-states into one, biased toward honesty.

    - any 'uncertain' present            -> 'uncertain'
    - 'filled' and 'empty' both present  -> 'uncertain' (conflict)
    - 'filled' present, no 'empty'       -> 'filled'
    - otherwise (all 'empty')            -> 'empty'
    """
    s = set(states)
    if "uncertain" in s:
        return "uncertain"
    if "filled" in s and "empty" in s:
        return "uncertain"
    if "filled" in s:
        return "filled"
    return "empty"


def merge_page_slots(conn: sqlite3.Connection, import_id: int) -> list[dict]:
    """Collapse all pages of an import into one deduped logical slot list.

    Parsed slots (year not None) are deduped by (year, mint, note) and their
    fill-states merged via :func:`_merge_fill`. Unparsed-label slots (year None)
    pass through unmerged -- they cannot be a set slot but must not be silently
    dropped. This list is the single review/commit source of truth.
    """
    rows = conn.execute(
        """
        SELECT s.year, s.mint, s.note, s.label_text, s.fill_state, s.confidence
        FROM album_page_slots s
        JOIN album_pages p ON s.page_id = p.id
        WHERE p.import_id = ?
        ORDER BY p.seq, s.slot_index
        """,
        (import_id,),
    ).fetchall()

    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    passthrough: list[dict] = []
    for r in rows:
        year = r["year"]
        mint = r["mint"]
        note = r["note"] or ""
        if year is None:
            passthrough.append(
                {
                    "year": None,
                    "mint": mint,
                    "note": note,
                    "label_text": r["label_text"] or "",
                    "fill_state": r["fill_state"],
                }
            )
            continue
        key = (year, mint, note)
        g = groups.get(key)
        if g is None:
            g = {
                "year": year,
                "mint": mint,
                "note": note,
                "label_text": r["label_text"] or "",
                "states": [],
            }
            groups[key] = g
            order.append(key)
        g["states"].append(r["fill_state"])
        if not g["label_text"] and r["label_text"]:
            g["label_text"] = r["label_text"]

    merged: list[dict] = []
    for key in order:
        g = groups[key]
        merged.append(
            {
                "year": g["year"],
                "mint": g["mint"],
                "note": g["note"],
                "label_text": g["label_text"],
                "fill_state": _merge_fill(g["states"]),
            }
        )
    merged.extend(passthrough)
    return merged


# ---------------------------------------------------------------------------
# 3. Manifest matching (pure)
# ---------------------------------------------------------------------------

def load_manifests(manifests_dir: str | Path | None = None) -> list[dict]:
    """Load and validate every shipped set manifest from core/sets/*.json."""
    directory = Path(manifests_dir) if manifests_dir else _SETS_DIR
    out: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "manifest.schema.json":
            continue
        try:
            out.append(load_manifest(path))
        except ManifestError:
            continue
    return out


def _photo_pairs(merged_slots: list[dict]) -> set[tuple[int, str]]:
    return {
        (s["year"], s["mint"])
        for s in merged_slots
        if s.get("year") is not None and s.get("mint") is not None
    }


def match_manifests(merged_slots: list[dict], manifests: list[dict]) -> list[dict]:
    """Score each manifest against the photographed slots, best first.

    ``containment`` = |photo ∩ manifest| / |photo parsed slots| -- how much of
    what was photographed the manifest explains (primary score: photos may cover
    only a subset of the folder). ``coverage`` = |photo ∩ manifest| / |manifest
    slots| -- how much of the manifest was photographed. Intersection is on
    (year, mint) pairs. Suggest-only: the human/UI applies any threshold.
    """
    photo = _photo_pairs(merged_slots)
    candidates: list[dict] = []
    for manifest in manifests:
        m_slots = manifest.get("slots", [])
        m_pairs = {(s["year"], s["mint"]) for s in m_slots}
        overlap = photo & m_pairs
        containment = len(overlap) / len(photo) if photo else 0.0
        coverage = len(overlap) / len(m_pairs) if m_pairs else 0.0
        missing_pairs = m_pairs - photo
        missing_from_photos = [
            {
                "year": s["year"],
                "mint": s["mint"],
                "note": s.get("note", ""),
                "key_date": bool(s.get("key_date")),
            }
            for s in m_slots
            if (s["year"], s["mint"]) in missing_pairs
        ]
        extra_in_photos = [
            {"year": y, "mint": m} for (y, m) in sorted(photo - m_pairs)
        ]
        candidates.append(
            {
                "manifest_id": manifest["id"],
                "name": manifest["name"],
                "score": round(containment, 4),
                "coverage": round(coverage, 4),
                "overlap": len(overlap),
                "missing_from_photos": missing_from_photos,
                "extra_in_photos": extra_in_photos,
            }
        )
    candidates.sort(
        key=lambda c: (-c["score"], -c["coverage"], c["manifest_id"])
    )
    return candidates


# ---------------------------------------------------------------------------
# 4. Commit (conn write)
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "album"


def _series_denomination(series: str | None) -> str | None:
    if series is None:
        return None
    return _SERIES_DENOMINATION.get(series)


def _find_manifest(manifest_id: str, manifests_dir: str | Path | None) -> dict:
    for manifest in load_manifests(manifests_dir):
        if manifest["id"] == manifest_id:
            return manifest
    raise AlbumError(f"unknown manifest_id: {manifest_id!r}")


def _synthesize_manifest(custom_name: str, merged_slots: list[dict]) -> dict:
    """Build a manifest dict from the parsed photo slots for a custom set.

    Unparseable-label slots (year None) are excluded -- they cannot be a slot
    without a year/mint. The series (best-effort) and composition_ref are unknown
    for an ad-hoc folder, so composition_ref defaults to 'unknown'.
    """
    slots: list[dict] = []
    seen: set[tuple] = set()
    for s in merged_slots:
        if s.get("year") is None or s.get("mint") is None:
            continue
        key = (s["year"], s["mint"], s.get("note", ""))
        if key in seen:
            continue
        seen.add(key)
        slot: dict = {"year": s["year"], "mint": s["mint"]}
        if s.get("note"):
            slot["note"] = s["note"]
        slots.append(slot)
    if not slots:
        raise AlbumError(
            "no parseable slots to build a custom set from (every label was "
            "unreadable)"
        )
    return {
        "id": "custom-" + _slugify(custom_name),
        "name": custom_name,
        "composition_ref": "unknown",
        "slots": slots,
    }


def _next_accession(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT 1 + COALESCE(MAX(CAST(substr(accession_no, 4) AS INTEGER)), 0)
        FROM coins
        """
    ).fetchone()
    return "NL-%06d" % row[0]


def _assign_coin(
    conn: sqlite3.Connection, set_id: int, coin_id: int, year: int, mint: str, note: str
) -> bool:
    """Assign a coin to its set slot. Returns True on success.

    Prefers the exact (year, mint, note) slot; falls back to a UNIQUE unfilled
    (year, mint) slot when the note differs (folder label vs manifest note). Only
    fills an empty slot; returns False when no unambiguous slot exists.
    """
    row = conn.execute(
        """
        SELECT id FROM set_slots
        WHERE set_id = ? AND year = ? AND mint = ? AND note = ? AND coin_id IS NULL
        """,
        (set_id, year, mint, note),
    ).fetchone()
    if row is None:
        rows = conn.execute(
            """
            SELECT id FROM set_slots
            WHERE set_id = ? AND year = ? AND mint = ? AND coin_id IS NULL
            """,
            (set_id, year, mint),
        ).fetchall()
        if len(rows) == 1:
            row = rows[0]
    if row is None:
        return False
    conn.execute("UPDATE set_slots SET coin_id = ? WHERE id = ?", (coin_id, row["id"]))
    return True


def commit_import(
    conn: sqlite3.Connection,
    import_id: int,
    *,
    manifest_id: str | None = None,
    custom_name: str | None = None,
    create_coins: bool = True,
    location_label: str | None = None,
    uncertain_policy: str = "block",
    manifests_dir: str | Path | None = None,
) -> dict:
    """Commit a reviewed import: create the set + slots and (optionally) coins.

    Exactly one of ``manifest_id`` / ``custom_name``. Uncertain slots block the
    commit (``uncertain_policy='block'`` -> :class:`AlbumUncertain`, mapped to
    409) unless ``uncertain_policy='empty'`` treats them as missing -- an
    uncertain slot NEVER becomes a filled coin. Filled slots create coin rows and
    are assigned to their set slot; a filled slot with no matching manifest slot
    still creates its coin (reported in ``unmatched_filled``, just not slotted).

    The whole commit -- set, slots, coins, events, and the import's committed
    status -- is one atomic transaction. Returns a summary dict.
    """
    if (manifest_id is None) == (custom_name is None):
        raise AlbumError("provide exactly one of manifest_id or custom_name")
    if uncertain_policy not in ("block", "empty"):
        raise AlbumError(f"invalid uncertain_policy: {uncertain_policy!r}")

    imp = conn.execute(
        "SELECT id, name, status FROM album_imports WHERE id = ?", (import_id,)
    ).fetchone()
    if imp is None:
        raise AlbumNotFound(import_id)
    if imp["status"] in ("committed", "discarded"):
        raise AlbumError(f"import {import_id} is already {imp['status']}")

    merged = merge_page_slots(conn, import_id)

    uncertain_count = sum(1 for s in merged if s["fill_state"] == "uncertain")
    if uncertain_count and uncertain_policy == "block":
        raise AlbumUncertain(uncertain_count)
    treated_uncertain_as_empty = uncertain_count if uncertain_policy == "empty" else 0

    skipped_unparsed = sum(1 for s in merged if s["year"] is None)
    # Filled parsed slots only. Uncertain -> never filled (either blocked above,
    # or under policy='empty' treated as missing).
    filled_slots = [
        s for s in merged if s["fill_state"] == "filled" and s["year"] is not None
    ]

    if manifest_id is not None:
        manifest = _find_manifest(manifest_id, manifests_dir)
    else:
        manifest = _synthesize_manifest(custom_name, merged)
        validate_manifest(manifest)  # schema-check the synthesized manifest

    set_key = manifest["id"]
    series = manifest.get("series")
    denomination = _series_denomination(series)

    now = _utcnow()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN IMMEDIATE")
    try:
        # --- set + slots (mirrors Ledger.load_set_manifest) ---
        conn.execute(
            """
            INSERT INTO sets (set_key, name, series, composition_ref)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(set_key) DO UPDATE SET
                name = excluded.name,
                series = excluded.series,
                composition_ref = excluded.composition_ref
            """,
            (set_key, manifest["name"], series, manifest["composition_ref"]),
        )
        set_id = conn.execute(
            "SELECT id FROM sets WHERE set_key = ?", (set_key,)
        ).fetchone()["id"]
        for slot in manifest["slots"]:
            note = slot.get("note", "")
            key_date = 1 if slot.get("key_date") else 0
            conn.execute(
                """
                INSERT INTO set_slots (set_id, year, mint, note, key_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(set_id, year, mint, note) DO UPDATE SET
                    key_date = excluded.key_date
                """,
                (set_id, slot["year"], slot["mint"], note, key_date),
            )

        # --- one location for the whole import ---
        loc_label = location_label or manifest["name"]
        loc_id = conn.execute(
            "INSERT INTO locations (parent_id, kind, label) VALUES (NULL, 'album', ?)",
            (loc_label,),
        ).lastrowid

        # --- coins for filled slots ---
        coins_created: list[str] = []
        unmatched_filled: list[dict] = []
        if create_coins:
            for s in filled_slots:
                year = s["year"]
                mint = s["mint"]
                note = s["note"]
                accession = _next_accession(conn)
                coin_notes = (
                    f"album-import:{import_id}"
                    + (f"; label {s['label_text']!r}" if s.get("label_text") else "")
                )
                cur = conn.execute(
                    """
                    INSERT INTO coins (
                        accession_no, series, year, mintmark, denomination,
                        country, acquired_source, location_id, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'US', ?, ?, ?, ?)
                    """,
                    (
                        accession,
                        series,
                        year,
                        mint,
                        denomination,
                        f"album-import:{import_id}",
                        loc_id,
                        coin_notes,
                        now,
                    ),
                )
                coin_id = cur.lastrowid
                conn.execute(
                    """
                    INSERT INTO events (coin_id, event_type, at, detail)
                    VALUES (?, 'added', ?, ?)
                    """,
                    (coin_id, now, json.dumps(loc_id)),
                )
                coins_created.append(accession)
                if not _assign_coin(conn, set_id, coin_id, year, mint, note):
                    unmatched_filled.append(
                        {
                            "accession": accession,
                            "year": year,
                            "mint": mint,
                            "note": note,
                        }
                    )

        # --- completion snapshot ---
        totals = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN coin_id IS NOT NULL THEN 1 ELSE 0 END) AS filled
            FROM set_slots WHERE set_id = ?
            """,
            (set_id,),
        ).fetchone()
        total_slots = totals["total"]
        filled = totals["filled"] or 0

        # --- mark the import committed + log the album event ---
        conn.execute(
            "UPDATE album_imports SET status = 'committed', set_id = ? WHERE id = ?",
            (set_id, import_id),
        )
        conn.execute(
            """
            INSERT INTO events (coin_id, event_type, at, detail)
            VALUES (NULL, 'album:committed', ?, ?)
            """,
            (
                now,
                json.dumps(
                    {
                        "import_id": import_id,
                        "set_key": set_key,
                        "set_id": set_id,
                        "coins_created": coins_created,
                    }
                ),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "set_key": set_key,
        "set_id": set_id,
        "total_slots": total_slots,
        "filled": filled,
        "missing_count": total_slots - filled,
        "coins_created": coins_created,
        "unmatched_filled": unmatched_filled,
        "skipped_unparsed": skipped_unparsed,
        "treated_uncertain_as_empty": treated_uncertain_as_empty,
    }


# ---------------------------------------------------------------------------
# 5. Needs (conn read)
# ---------------------------------------------------------------------------

def _resolve_set(conn: sqlite3.Connection, set_id: int | str) -> sqlite3.Row:
    if isinstance(set_id, int):
        row = conn.execute(
            "SELECT id, set_key, name FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, set_key, name FROM sets WHERE set_key = ?", (set_id,)
        ).fetchone()
    if row is None:
        raise SetNotFound(set_id)
    return row


def needs(conn: sqlite3.Connection, set_id: int | str) -> dict:
    """What a set is still missing, built on the set_slots gap query.

    Returns the set identity, completion counts, a ``completion_pct`` (0-100, one
    decimal), the ordered list of missing slots (year, mint, note, key_date), and
    how many of those missing slots are key dates.
    """
    meta = _resolve_set(conn, set_id)
    sid = meta["id"]
    totals = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN coin_id IS NOT NULL THEN 1 ELSE 0 END) AS filled
        FROM set_slots WHERE set_id = ?
        """,
        (sid,),
    ).fetchone()
    total = totals["total"]
    filled = totals["filled"] or 0
    gaps = conn.execute(
        """
        SELECT year, mint, note, key_date FROM set_slots
        WHERE set_id = ? AND coin_id IS NULL
        ORDER BY year, mint, note
        """,
        (sid,),
    ).fetchall()
    missing = [
        {
            "year": g["year"],
            "mint": g["mint"],
            "note": g["note"],
            "key_date": bool(g["key_date"]),
        }
        for g in gaps
    ]
    key_dates_missing = sum(1 for g in gaps if g["key_date"])
    completion_pct = round(100.0 * filled / total, 1) if total else 0.0
    return {
        "set_key": meta["set_key"],
        "name": meta["name"],
        "total_slots": total,
        "filled": filled,
        "completion_pct": completion_pct,
        "missing": missing,
        "key_dates_missing": key_dates_missing,
    }
