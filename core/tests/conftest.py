"""Shared pytest fixtures for numislens_core tests."""

import pytest

from numislens_core.ledger import Ledger


@pytest.fixture
def ledger(tmp_path):
    db_path = tmp_path / "test.db"
    led = Ledger(db_path)
    yield led
    led.close()
