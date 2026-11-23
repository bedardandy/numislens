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
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


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


def test_every_api_operation_requires_the_token(client: TestClient) -> None:
    """Behavioral guard for the "every /api/v1 path needs the bearer" rule.

    Calls every operation the app really serves (taken from its own schema)
    with no token. The exported spec's "all secured" check only asserts that a
    security block was written into the JSON; this asserts the 401.
    """
    import re

    checked = 0
    for path, item in client.app.openapi()["paths"].items():
        assert path.startswith("/api/v1"), path
        concrete = re.sub(r"\{[^}]+\}", "1", path)
        for method in item:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            response = client.request(method.upper(), concrete)
            assert response.status_code == 401, f"{method.upper()} {path}"
            checked += 1
    assert checked > 40  # the walk really covered the API


def test_schema_and_docs_are_not_served_without_the_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/v1/openapi.json").status_code == 401
    for path in ("/api/v1/docs", "/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
    spec = client.get("/api/v1/openapi.json", headers=auth_headers)
    assert spec.status_code == 200
    assert "/api/v1/coins" in spec.json()["paths"]


def test_non_ascii_token_is_a_401_not_a_500(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer t\xe9".encode("latin-1")},
    )
    assert response.status_code == 401
