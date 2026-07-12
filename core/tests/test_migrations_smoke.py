"""Smoke tests for database migrations."""

from numislens_core import migrate

EXPECTED_TABLES = {
    "compositions",
    "locations",
    "coins",
    "sets",
    "set_slots",
    "spot_prices",
    "appraisals",
    "events",
    "coin_images",
}


def test_migrations_smoke(tmp_path):
    db_path = tmp_path / "test.db"

    applied = migrate(db_path)
    assert len(applied) == 4
    assert "001_initial.sql" in applied
    assert "002_seed_compositions.sql" in applied
    assert "003_seed_steel_cent.sql" in applied
    assert "004_stale_columns.sql" in applied

    conn = __import__("sqlite3").connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert EXPECTED_TABLES <= tables

        count = conn.execute("SELECT COUNT(*) FROM compositions").fetchone()[0]
        assert count == 16

        steel = conn.execute(
            "SELECT precious_weight_ozt FROM compositions WHERE name = ?",
            ("Steel cent",),
        ).fetchone()
        assert steel is not None
        assert steel[0] is None

        row = conn.execute(
            "SELECT precious_weight_ozt FROM compositions WHERE name = ?",
            ("90% silver dollar",),
        ).fetchone()
        assert row[0] == 0.77344

        coin_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(coins)").fetchall()
        }
        assert {"stale_since", "stale_reason"} <= coin_cols
    finally:
        conn.close()

    applied_again = migrate(db_path)
    assert applied_again == []
