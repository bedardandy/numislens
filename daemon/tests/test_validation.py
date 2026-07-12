"""Request validation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_bad_grade_bucket_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/coins",
        json={"grade_bucket": "ZZZ"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "grade_bucket" in response.json()["detail"]


def test_bad_value_basis_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/coins",
        json={"value_basis": "bogus"},
        headers=auth_headers,
    )
    assert response.status_code == 422
