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


def test_unknown_field_rejected(client, auth_headers):
    """Typo'd/guessed field names must 422, never silently drop (e.g. 'mint' vs 'mintmark')."""
    resp = client.post(
        "/api/v1/coins",
        json={"series": "Peace Dollar", "year": 1922, "mint": "P", "composition_id": 4},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "mint" in resp.text
