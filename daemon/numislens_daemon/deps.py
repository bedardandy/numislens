"""FastAPI dependencies for the NumisLens daemon."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from numislens_core import Ledger


def get_ledger(request: Request) -> Generator[Ledger, None, None]:
    # create_app() migrated the database once at startup; skip the per-request
    # migration scan here.
    ldb = Ledger(request.app.state.db_path, migrate=False)
    ldb.conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield ldb
    finally:
        ldb.close()
