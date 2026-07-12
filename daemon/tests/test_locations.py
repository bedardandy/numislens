"""Location endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "B3"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"]
    assert body["path"] == "B3"


def test_location_tree(client: TestClient, auth_headers: dict[str, str]) -> None:
    parent = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "Parent"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]
    client.post(
        "/api/v1/locations",
        json={"kind": "slot", "label": "Child", "parent_id": parent_id},
        headers=auth_headers,
    )

    response = client.get("/api/v1/locations/tree", headers=auth_headers)
    assert response.status_code == 200
    tree = response.json()["tree"]
    assert len(tree) == 1
    assert len(tree[0]["children"]) == 1


def test_location_contents_recursive(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    box = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "Box"},
        headers=auth_headers,
    )
    box_id = box.json()["id"]
    slot = client.post(
        "/api/v1/locations",
        json={"kind": "slot", "label": "Slot", "parent_id": box_id},
        headers=auth_headers,
    )
    slot_id = slot.json()["id"]
    make_coin({"location_id": slot_id})

    recursive = client.get(
        f"/api/v1/locations/{box_id}",
        params={"recursive": True},
        headers=auth_headers,
    )
    assert recursive.status_code == 200
    assert len(recursive.json()["contents"]) >= 1

    direct = client.get(
        f"/api/v1/locations/{box_id}",
        params={"recursive": False},
        headers=auth_headers,
    )
    assert direct.status_code == 200
    assert direct.json()["contents"] == []


def test_location_unknown_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/locations/999999", headers=auth_headers)
    assert response.status_code == 404
