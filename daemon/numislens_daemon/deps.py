"""FastAPI dependencies for the NumisLens daemon."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from numislens_core import Ledger


def get_ledger(request: Request) -> Generator[Ledger, None, None]:
    ldb = Ledger(request.app.state.db_path)
    ldb.conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield ldb
    finally:
        ldb.close()
