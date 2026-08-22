"""Export/import endpoint tests (CSV data portability)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_export_import_roundtrip(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()  # Peace Dollar 1921, composition 4 = '90% silver dollar'
    loc = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "Box 1"},
        headers=auth_headers,
    ).json()
    loc_id = loc["id"]
    client.put(f"/api/v1/coins/{acc}", json={"location_id": loc_id}, headers=auth_headers)
    client.post(
        f"/api/v1/coins/{acc}/disposition",
        json={"disposition": "sold", "sold_price_cents": 25000, "sold_venue": "eBay"},
        headers=auth_headers,
    )

    export = client.get("/api/v1/export/coins.csv", headers=auth_headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert 'filename="numislens-coins-' in export.headers["content-disposition"]
    csv_text = export.text

    imported = client.post(
        "/api/v1/import/coins.csv",
        files={"file": ("coins.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=auth_headers,
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["count"] == 1
    new_acc = body["created"][0]
    assert new_acc != acc  # accessions are server-assigned

    original = client.get(f"/api/v1/coins/{acc}", headers=auth_headers).json()
    copy = client.get(f"/api/v1/coins/{new_acc}", headers=auth_headers).json()
    for field in (
        "series", "year", "mintmark", "denomination", "cost_basis_cents",
        "disposition", "sold_price_cents", "sold_venue",
    ):
        assert copy[field] == original[field], field
    assert copy["composition_id"] == original["composition_id"] == 4
    assert copy["location_id"] == loc_id


def test_import_unknown_column_422(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/import/coins.csv",
        files={"file": ("x.csv", b"series,mint\nMorgan,P\n", "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("mint" in e for e in detail["errors"])
    assert any("unknown column" in e for e in detail["errors"])


def test_import_is_all_or_nothing(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    before = client.get("/api/v1/coins", headers=auth_headers).json()
    csv_text = (
        "series,year\n"
        "Morgan Dollar,1885\n"
        "Peace Dollar,notayear\n"
    ).encode("utf-8")
    response = client.post(
        "/api/v1/import/coins.csv",
        files={"file": ("x.csv", csv_text, "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert any("row 3" in e for e in response.json()["detail"]["errors"])
    after = client.get("/api/v1/coins", headers=auth_headers).json()
    # The valid row must NOT have been created — nothing was.
    assert len(after) == len(before)


def test_import_rejects_non_csv_content_type(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/import/coins.csv",
        files={"file": ("x.txt", b"series,year\nMorgan,1885\n", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "text/csv" in response.json()["detail"]


def test_export_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/export/coins.csv").status_code == 401
