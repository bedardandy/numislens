"""Set manifest and assignment tests."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

MANIFEST = {
    "id": "test-set",
    "name": "Test Set",
    "composition_ref": "90% silver dollar",
    "slots": [
        {"year": 1921, "mint": "P"},
        {"year": 1922, "mint": "D", "key_date": True},
    ],
}


def test_set_load_inline_and_gaps(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    load = client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST},
        headers=auth_headers,
    )
    assert load.status_code == 200
    set_id = load.json()["set_id"]

    gaps = client.get(f"/api/v1/sets/{set_id}/gaps", headers=auth_headers)
    assert gaps.status_code == 200
    assert len(gaps.json()["gaps"]) == 2


def test_set_load_via_path(
    client: TestClient, auth_headers: dict[str, str], tmp_path
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST), encoding="utf-8")
    response = client.post(
        "/api/v1/sets/load",
        json={"manifest_path": str(manifest_path)},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_set_assign_and_status(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    load = client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST},
        headers=auth_headers,
    )
    set_id = load.json()["set_id"]
    acc = make_coin()

    assign = client.post(
        f"/api/v1/sets/{set_id}/assign",
        json={"slot": {"year": 1921, "mint": "P"}, "accession": acc},
        headers=auth_headers,
    )
    assert assign.status_code == 200
    assert assign.json()["filled"] == 1

    status = client.get(f"/api/v1/sets/{set_id}/status", headers=auth_headers)
    assert status.status_code == 200
    body = status.json()
    assert body["filled"] == 1
    assert body["total"] == 2
    assert body["gaps"] == 1


def test_set_board(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    load = client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST},
        headers=auth_headers,
    )
    set_id = load.json()["set_id"]
    acc = make_coin({"grade_bucket": "VF"})

    assign = client.post(
        f"/api/v1/sets/{set_id}/assign",
        json={"slot": {"year": 1921, "mint": "P"}, "accession": acc},
        headers=auth_headers,
    )
    assert assign.status_code == 200

    board = client.get(f"/api/v1/sets/{set_id}/board", headers=auth_headers)
    assert board.status_code == 200
    body = board.json()
    assert body["filled"] == 1
    assert body["total"] == 2
    assert len(body["slots"]) == 2

    assigned = next(s for s in body["slots"] if s["year"] == 1921 and s["mint"] == "P")
    assert assigned["accession"] == acc
    assert assigned["grade_bucket"] == "VF"

    unassigned = next(s for s in body["slots"] if s["year"] == 1922 and s["mint"] == "D")
    assert unassigned["accession"] is None


def test_set_assign_already_filled_422(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    load = client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST},
        headers=auth_headers,
    )
    set_id = load.json()["set_id"]
    first = make_coin()
    second = make_coin()

    first_assign = client.post(
        f"/api/v1/sets/{set_id}/assign",
        json={"slot": {"year": 1921, "mint": "P"}, "accession": first},
        headers=auth_headers,
    )
    assert first_assign.status_code == 200

    second_assign = client.post(
        f"/api/v1/sets/{set_id}/assign",
        json={"slot": {"year": 1921, "mint": "P"}, "accession": second},
        headers=auth_headers,
    )
    assert second_assign.status_code == 422
    assert "already filled" in second_assign.json()["detail"]


def test_set_load_both_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST, "manifest_path": "/x"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_set_load_neither_422(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/sets/load", json={}, headers=auth_headers)
    assert response.status_code == 422


def test_set_load_invalid_manifest_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/sets/load",
        json={"manifest": {"id": "x"}},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_sets_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post(
        "/api/v1/sets/load",
        json={"manifest": MANIFEST},
        headers=auth_headers,
    )
    response = client.get("/api/v1/sets", headers=auth_headers)
    assert response.status_code == 200
    sets = response.json()
    match = next(s for s in sets if s["set_key"] == "test-set")
    assert match["total"] == 2
