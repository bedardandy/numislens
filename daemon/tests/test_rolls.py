"""Coin-roll endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_rolls_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/rolls").status_code == 401
    assert client.post("/api/v1/rolls", json={"denomination": "cent", "count": 50}).status_code == 401


def test_create_get_patch_pull_happy_path(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50},
        headers=auth_headers,
    )
    assert created.status_code == 201
    roll = created.json()
    assert roll["roll_no"] == "NR-000001"
    assert roll["status"] == "unopened"
    assert roll["count"] == 50
    assert roll["face_cents"] == 500

    got = client.get("/api/v1/rolls/NR-000001", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["roll_no"] == "NR-000001"

    listed = client.get("/api/v1/rolls", headers=auth_headers)
    assert listed.status_code == 200
    assert [r["roll_no"] for r in listed.json()] == ["NR-000001"]

    patched = client.patch(
        "/api/v1/rolls/NR-000001",
        json={"status": "searching", "notes": "half searched"},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "searching"
    assert patched.json()["notes"] == "half searched"

    # status filter reflects the patch
    searching = client.get(
        "/api/v1/rolls", params={"status": "searching"}, headers=auth_headers
    )
    assert [r["roll_no"] for r in searching.json()] == ["NR-000001"]

    pulled = client.post(
        "/api/v1/rolls/NR-000001/pull",
        json={"count": 10},
        headers=auth_headers,
    )
    assert pulled.status_code == 200
    assert pulled.json()["roll"]["count"] == 40
    assert pulled.json()["coins_created"] == []


def test_pull_with_quick_creates_coins_sourced_to_roll(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/rolls",
        json={"denomination": "cent", "count": 50},
        headers=auth_headers,
    )
    resp = client.post(
        "/api/v1/rolls/NR-000001/pull",
        json={"count": 2, "quick": ["1943 steel cent", "1909 Lincoln wheat cent"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["roll"]["count"] == 48
    accs = body["coins_created"]
    assert len(accs) == 2

    for acc in accs:
        coin = client.get(f"/api/v1/coins/{acc}", headers=auth_headers).json()
        assert coin["acquired_source"] == "NR-000001"


def test_pull_quick_longer_than_count_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/rolls",
        json={"denomination": "cent", "count": 50},
        headers=auth_headers,
    )
    resp = client.post(
        "/api/v1/rolls/NR-000001/pull",
        json={"count": 1, "quick": ["1943 steel cent", "1909 wheat cent"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_pull_unparseable_quick_422_before_mutation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/rolls",
        json={"denomination": "cent", "count": 50},
        headers=auth_headers,
    )
    resp = client.post(
        "/api/v1/rolls/NR-000001/pull",
        json={"count": 2, "quick": ["something unparseable"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    # roll must be untouched (no partial pull)
    roll = client.get("/api/v1/rolls/NR-000001", headers=auth_headers).json()
    assert roll["count"] == 50


def test_create_unknown_composition_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50, "composition_name": "nope"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_bad_count_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_extra_field_rejected_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50, "mint": "P"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_unknown_roll_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    assert (
        client.get("/api/v1/rolls/NR-999999", headers=auth_headers).status_code == 404
    )


def test_patch_unknown_roll_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/api/v1/rolls/NR-999999",
        json={"status": "searching"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_patch_invalid_status_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50},
        headers=auth_headers,
    )
    resp = client.patch(
        "/api/v1/rolls/NR-000001",
        json={"status": "bogus"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_pull_unknown_roll_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/v1/rolls/NR-999999/pull",
        json={"count": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_roll_labels_pdf_all_and_filtered(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50},
        headers=auth_headers,
    )
    client.post(
        "/api/v1/rolls",
        json={"denomination": "quarter", "count": 40, "variant": "silver"},
        headers=auth_headers,
    )

    all_pdf = client.get("/api/v1/labels/rolls.pdf", headers=auth_headers)
    assert all_pdf.status_code == 200
    assert all_pdf.headers["content-type"] == "application/pdf"
    assert all_pdf.content.startswith(b"%PDF")

    filtered = client.get(
        "/api/v1/labels/rolls.pdf",
        params={"rolls": ["NR-000002"]},
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert filtered.content.startswith(b"%PDF")


def test_roll_labels_qr_uses_public_url_env(
    client, auth_headers, monkeypatch
) -> None:
    from numislens_daemon import labels as labels_mod

    captured: list[str] = []
    real = labels_mod._qr_png_bytes
    monkeypatch.setattr(
        labels_mod,
        "_qr_png_bytes",
        lambda data: captured.append(data) or real(data),
    )
    client.post(
        "/api/v1/rolls",
        json={"denomination": "dime", "count": 50},
        headers=auth_headers,
    )
    monkeypatch.setenv("NUMISLENS_PUBLIC_URL", "https://numislens.tailnet.example")
    resp = client.get("/api/v1/labels/rolls.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert captured and captured[0] == "https://numislens.tailnet.example/r/NR-000001"


def test_roll_labels_unknown_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get(
        "/api/v1/labels/rolls.pdf",
        params={"rolls": ["NR-999999"]},
        headers=auth_headers,
    )
    assert resp.status_code == 404
