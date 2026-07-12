"""Pytest fixtures for the NumisLens daemon."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from numislens_daemon.app import create_app


@pytest.fixture
def token() -> str:
    return "test-token-123"


@pytest.fixture
def client(tmp_path, token: str) -> TestClient:
    db_path = tmp_path / "test.db"
    app = create_app(db_path=db_path, token=token)
    return TestClient(app)


@pytest.fixture
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
