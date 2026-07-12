"""SQLite migration runner and connection helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a database connection with foreign keys enabled."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(path: str | Path) -> list[str]:
    """Apply pending SQL migrations and return filenames applied this call.

    Each migration file plus its bookkeeping row is applied inside a single
    atomic transaction: if any statement in a migration fails, the whole
    migration is rolled back and the exception propagates (fail-loud). Running
    twice applies nothing the second time (idempotent).
    """
    path = Path(path)
    # isolation_level=None -> autocommit; we manage transactions explicitly so
    # that executescript() does not silently COMMIT mid-migration.
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              filename TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            )
            """
        )

        already_applied = {
            row[0]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        newly_applied: list[str] = []

        for migration_file in migration_files:
            filename = migration_file.name
            if filename in already_applied:
                continue

            sql = migration_file.read_text(encoding="utf-8")
            applied_at = datetime.now(timezone.utc).isoformat()
            # executescript() COMMITs any pending transaction before it runs, so
            # BEGIN/COMMIT must live INSIDE the script to make the migration plus
            # its bookkeeping row a single atomic unit. Literals are ours (a
            # filename and a timestamp); double any single quote defensively.
            fn = filename.replace("'", "''")
            ts = applied_at.replace("'", "''")
            script = (
                "BEGIN;\n"
                + sql
                + f"\nINSERT INTO schema_migrations (filename, applied_at) "
                + f"VALUES ('{fn}', '{ts}');\nCOMMIT;\n"
            )
            try:
                conn.executescript(script)
            except Exception:
                # Roll back the partially-applied migration; fail loud.
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise

            newly_applied.append(filename)

        return newly_applied
    finally:
        conn.close()


def init_db(path: str | Path) -> sqlite3.Connection:
    """Migrate the database and return a configured connection."""
    migrate(path)
    return connect(path)
