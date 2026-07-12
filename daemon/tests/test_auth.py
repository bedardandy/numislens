"""Authentication and startup tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from numislens_daemon.app import create_app


def test_health_without_auth_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 401


def test_health_with_wrong_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_health_with_correct_token_returns_ok(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/health", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_without_token_raises_runtime_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NUMISLENS_TOKEN", raising=False)
    # app.py imported resolve_token by name, so patch the reference it actually
    # calls (not the one in the config module).
    monkeypatch.setattr(
        "numislens_daemon.app.resolve_token",
        lambda: None,
    )
    with pytest.raises(RuntimeError, match="no bearer token configured"):
        create_app(db_path=tmp_path / "test.db", token=None)


def test_static_index_without_auth_returns_200(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
