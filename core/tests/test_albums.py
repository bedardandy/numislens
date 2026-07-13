"""Tests for the album / coin-folder import logic (pure + conn-based)."""

from __future__ import annotations

import pytest

from numislens_core import albums
from numislens_core.albums import (
    AlbumError,
    AlbumUncertain,
    extract_century_hint,
    parse_slot_label,
)

_NOW = "2026-07-13T00:00:00+00:00"


# ---------------------------------------------------------------------------
# helpers: seed an import with pages + slots directly (core has no CRUD API)
# ---------------------------------------------------------------------------

def _make_import(conn, name="Test Album"):
    cur = conn.execute(
        "INSERT INTO album_imports (name, status, created_at) VALUES (?, 'pending', ?)",
        (name, _NOW),
    )
    conn.commit()
    return cur.lastrowid


def _add_page(conn, import_id, *, seq=1, title=None, slots=()):
    cur = conn.execute(
        """
        INSERT INTO album_pages
            (import_id, seq, content_hash, path, page_title, page_type, analyzed_at)
        VALUES (?, ?, ?, ?, ?, 'page', ?)
        """,
        (import_id, seq, f"hash-{seq}", f"/x/{seq}.jpg", title, _NOW),
    )
    page_id = cur.lastrowid
    for i, s in enumerate(slots):
        conn.execute(
            """
            INSERT INTO album_page_slots
                (page_id, slot_index, label_text, year, mint, note, fill_state,
                 confidence, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'vision')
            """,
            (
                page_id,
                i,
                s.get("label_text", ""),
                s.get("year"),
                s.get("mint"),
                s.get("note", ""),
                s["fill_state"],
                s.get("confidence"),
            ),
        )
    conn.commit()
    return page_id


def _slot(year, mint, fill_state, note="", label_text=""):
    return {
        "year": year,
        "mint": mint,
        "note": note,
        "fill_state": fill_state,
        "label_text": label_text or (f"{year} {mint}" if year else ""),
    }


# ---------------------------------------------------------------------------
# 1. parse_slot_label + extract_century_hint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,hint,expected",
    [
        ("1943 D", None, (1943, "D", "")),
        ("1916", None, (1916, "P", "")),          # folders omit the P mark
        ("1909 S V.D.B.", None, (1909, "S", "VDB")),
        ("1885-CC", None, (1885, "CC", "")),       # hyphen year-mint form
        ("1909-S", None, (1909, "S", "")),
        ("1922 No D", None, (1922, "D", "No")),      # note-carrying variety
        ("'43", None, None),                        # two-digit, no hint -> None
        ("43 D", None, None),                       # two-digit, no hint -> None
        ("43 D", 1900, (1943, "D", "")),            # two-digit + hint resolves
        ("'58", 1900, (1958, "P", "")),
        ("", None, (None, None, "")),
        ("glare blur", None, (None, None, "glare blur")),
    ],
)
def test_parse_slot_label(text, hint, expected):
    result = parse_slot_label(text, hint)
    if expected is None:
        # Sentinel: assert only that the YEAR did not resolve.
        assert result[0] is None
    else:
        assert result == expected


def test_parse_never_invents_year_without_hint():
    # A two-digit label is unparseable without a century hint -- the original
    # text is preserved, not a fabricated year.
    year, mint, note = parse_slot_label("43 D")
    assert year is None
    assert note == "43 D"


def test_extract_century_hint():
    assert extract_century_hint("LINCOLN CENTS 1941-1958") == 1900
    assert extract_century_hint("Morgan Dollars 1878-1921") == 1800
    assert extract_century_hint("No year here") is None
    assert extract_century_hint("") is None


# ---------------------------------------------------------------------------
# 2. merge_page_slots
# ---------------------------------------------------------------------------

def test_merge_conflict_is_uncertain(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, seq=1, slots=[_slot(1943, "D", "filled")])
    _add_page(conn, imp, seq=2, slots=[_slot(1943, "D", "empty")])
    merged = albums.merge_page_slots(conn, imp)
    assert len(merged) == 1
    assert merged[0]["fill_state"] == "uncertain"


def test_merge_filled_wins_when_no_empty(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, seq=1, slots=[_slot(1909, "S", "filled")])
    _add_page(conn, imp, seq=2, slots=[_slot(1909, "S", "empty", note="x")])  # diff note
    _add_page(conn, imp, seq=3, slots=[_slot(1909, "S", "empty")])
    _add_page(conn, imp, seq=4, slots=[_slot(1909, "S", "filled")])
    merged = albums.merge_page_slots(conn, imp)
    by_key = {(m["year"], m["mint"], m["note"]): m for m in merged}
    # (1909,S,'') saw filled+empty -> uncertain
    assert by_key[(1909, "S", "")]["fill_state"] == "uncertain"
    # (1909,S,'x') only empty
    assert by_key[(1909, "S", "x")]["fill_state"] == "empty"


def test_merge_unparsed_pass_through(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(
        conn,
        imp,
        slots=[
            _slot(None, None, "empty", label_text="blurry"),
            _slot(None, None, "empty", label_text="blurry too"),
        ],
    )
    merged = albums.merge_page_slots(conn, imp)
    # Unparsed slots pass through unmerged (2 distinct entries).
    assert sum(1 for m in merged if m["year"] is None) == 2


# ---------------------------------------------------------------------------
# 3. match_manifests
# ---------------------------------------------------------------------------

def test_match_manifests_lincoln_top_candidate():
    manifests = albums.load_manifests()
    # A 20-slot subset of the real Lincoln wheat set (1911-1920 all have P+D).
    years = list(range(1911, 1921))
    photo = []
    for y in years:
        photo.append({"year": y, "mint": "P", "note": "", "fill_state": "filled"})
        photo.append({"year": y, "mint": "D", "note": "", "fill_state": "empty"})
    candidates = albums.match_manifests(photo, manifests)
    top = candidates[0]
    assert top["manifest_id"] == "lincoln-wheat-1909-1958"
    # Every photographed pair present in Lincoln -> containment 1.0.
    assert top["score"] == pytest.approx(1.0)
    # Coverage is a fraction (subset of the full folder).
    assert 0.0 < top["coverage"] < 1.0
    assert top["overlap"] == len(albums._photo_pairs(photo))


def test_match_manifests_reports_missing_and_extra():
    manifests = [
        {
            "id": "mini",
            "name": "Mini",
            "composition_ref": "x",
            "slots": [
                {"year": 1909, "mint": "P"},
                {"year": 1909, "mint": "S", "key_date": True},
            ],
        }
    ]
    photo = [
        {"year": 1909, "mint": "P", "note": "", "fill_state": "filled"},
        {"year": 1999, "mint": "P", "note": "", "fill_state": "filled"},  # extra
    ]
    cand = albums.match_manifests(photo, manifests)[0]
    assert cand["score"] == pytest.approx(0.5)  # 1 of 2 photo pairs in manifest
    assert cand["coverage"] == pytest.approx(0.5)  # 1 of 2 manifest pairs shot
    missing = {(m["year"], m["mint"]) for m in cand["missing_from_photos"]}
    assert (1909, "S") in missing
    assert {(e["year"], e["mint"]) for e in cand["extra_in_photos"]} == {(1999, "P")}


# ---------------------------------------------------------------------------
# 4. commit_import
# ---------------------------------------------------------------------------

def test_commit_manifest_happy_path(ledger):
    conn = ledger.conn
    imp = _make_import(conn, name="Wheaties")
    _add_page(
        conn,
        imp,
        title="LINCOLN CENTS 1909-1958",
        slots=[
            _slot(1909, "P", "filled"),
            _slot(1909, "S", "filled"),
            _slot(1943, "D", "empty"),
        ],
    )
    summary = albums.commit_import(
        conn, imp, manifest_id="lincoln-wheat-1909-1958"
    )
    assert summary["set_key"] == "lincoln-wheat-1909-1958"
    assert summary["filled"] == 2
    assert len(summary["coins_created"]) == 2
    assert summary["unmatched_filled"] == []
    assert summary["total_slots"] > 100  # full wheat folder

    # coins carry the album provenance + were slotted.
    for acc in summary["coins_created"]:
        coin = ledger.get_coin(acc)
        assert coin["acquired_source"] == f"album-import:{imp}"
        assert coin["series"] == "Lincoln Wheat Cent"
        assert coin["denomination"] == "cent"
        assert coin["country"] == "US"
        # created/found location is an 'album' location.
        loc = conn.execute(
            "SELECT kind, label FROM locations WHERE id = ?", (coin["location_id"],)
        ).fetchone()
        assert loc["kind"] == "album"

    # needs() reflects the two filled slots.
    n = albums.needs(conn, summary["set_id"])
    assert n["filled"] == 2
    assert n["total_slots"] == summary["total_slots"]
    assert 0.0 < n["completion_pct"] < 100.0
    # 1914-D is a key date and still missing.
    assert n["key_dates_missing"] >= 1

    # import marked committed + set_id set.
    row = conn.execute(
        "SELECT status, set_id FROM album_imports WHERE id = ?", (imp,)
    ).fetchone()
    assert row["status"] == "committed"
    assert row["set_id"] == summary["set_id"]

    # append-only album:committed event with coin_id NULL + import_id in detail.
    ev = conn.execute(
        "SELECT coin_id, detail FROM events WHERE event_type = 'album:committed'"
    ).fetchone()
    assert ev["coin_id"] is None
    import json

    assert json.loads(ev["detail"])["import_id"] == imp


def test_commit_custom_set(ledger):
    conn = ledger.conn
    imp = _make_import(conn, name="My Junk Box")
    _add_page(
        conn,
        imp,
        slots=[
            _slot(1970, "P", "filled"),
            _slot(1971, "D", "empty"),
        ],
    )
    summary = albums.commit_import(conn, imp, custom_name="My Junk Box")
    assert summary["set_key"] == "custom-my-junk-box"
    assert summary["total_slots"] == 2
    assert summary["filled"] == 1
    n = albums.needs(conn, summary["set_id"])
    assert n["name"] == "My Junk Box"
    assert n["filled"] == 1
    assert n["total_slots"] == 2


def test_commit_blocks_on_uncertain(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(
        conn,
        imp,
        slots=[
            _slot(1909, "P", "filled"),
            _slot(1914, "D", "uncertain"),
        ],
    )
    with pytest.raises(AlbumUncertain):
        albums.commit_import(conn, imp, manifest_id="lincoln-wheat-1909-1958")
    # nothing was committed.
    row = conn.execute(
        "SELECT status FROM album_imports WHERE id = ?", (imp,)
    ).fetchone()
    assert row["status"] == "pending"


def test_commit_uncertain_policy_empty(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(
        conn,
        imp,
        slots=[
            _slot(1909, "P", "filled"),
            _slot(1914, "D", "uncertain"),
        ],
    )
    summary = albums.commit_import(
        conn,
        imp,
        manifest_id="lincoln-wheat-1909-1958",
        uncertain_policy="empty",
    )
    assert summary["treated_uncertain_as_empty"] == 1
    # The uncertain 1914-D never became a coin.
    assert summary["filled"] == 1
    n = albums.needs(conn, summary["set_id"])
    missing = {(m["year"], m["mint"]) for m in n["missing"]}
    assert (1914, "D") in missing


def test_commit_unmatched_filled(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(
        conn,
        imp,
        slots=[
            _slot(1909, "P", "filled"),   # in the manifest -> slotted
            _slot(1800, "P", "filled"),   # NOT in the manifest -> unmatched
        ],
    )
    summary = albums.commit_import(
        conn, imp, manifest_id="lincoln-wheat-1909-1958"
    )
    assert len(summary["coins_created"]) == 2  # both coins created
    assert len(summary["unmatched_filled"]) == 1
    assert summary["unmatched_filled"][0]["year"] == 1800
    assert summary["filled"] == 1  # only the matched one is slotted


def test_commit_skipped_unparsed(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(
        conn,
        imp,
        slots=[
            _slot(1909, "P", "filled"),
            _slot(None, None, "empty", label_text="unreadable"),
        ],
    )
    summary = albums.commit_import(
        conn, imp, manifest_id="lincoln-wheat-1909-1958"
    )
    assert summary["skipped_unparsed"] == 1


def test_commit_requires_exactly_one_target(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, slots=[_slot(1909, "P", "filled")])
    with pytest.raises(AlbumError):
        albums.commit_import(conn, imp)  # neither
    with pytest.raises(AlbumError):
        albums.commit_import(
            conn, imp, manifest_id="lincoln-wheat-1909-1958", custom_name="X"
        )


def test_commit_twice_fails(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, slots=[_slot(1909, "P", "filled")])
    albums.commit_import(conn, imp, manifest_id="lincoln-wheat-1909-1958")
    with pytest.raises(AlbumError):
        albums.commit_import(conn, imp, manifest_id="lincoln-wheat-1909-1958")


def test_commit_no_create_coins(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, slots=[_slot(1909, "P", "filled")])
    summary = albums.commit_import(
        conn, imp, manifest_id="lincoln-wheat-1909-1958", create_coins=False
    )
    assert summary["coins_created"] == []
    assert summary["filled"] == 0


def test_events_are_append_only(ledger):
    conn = ledger.conn
    imp = _make_import(conn)
    _add_page(conn, imp, slots=[_slot(1909, "P", "filled")])
    albums.commit_import(conn, imp, manifest_id="lincoln-wheat-1909-1958")
    ev_id = conn.execute(
        "SELECT id FROM events WHERE event_type = 'album:committed'"
    ).fetchone()["id"]
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE events SET event_type = 'x' WHERE id = ?", (ev_id,))
        conn.commit()


def test_needs_unknown_set_raises(ledger):
    from numislens_core import SetNotFound

    with pytest.raises(SetNotFound):
        albums.needs(ledger.conn, "no-such-set")
