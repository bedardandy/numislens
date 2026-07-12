"""Label PDF endpoint tests."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient


def test_labels_by_accessions(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    response = client.get(
        "/api/v1/labels.pdf",
        params={"accessions": acc},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    pages = re.findall(rb"/Type\s*/Page(?![s])", response.content)
    assert len(pages) >= 1


def test_labels_by_location(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    box = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "LabelBox"},
        headers=auth_headers,
    )
    box_id = box.json()["id"]
    client.post(
        f"/api/v1/coins/{acc}/move",
        json={"location_id": box_id},
        headers=auth_headers,
    )

    response = client.get(
        "/api/v1/labels.pdf",
        params={"location_id": box_id},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_labels_requires_exactly_one_param(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    neither = client.get("/api/v1/labels.pdf", headers=auth_headers)
    assert neither.status_code == 422

    both = client.get(
        "/api/v1/labels.pdf",
        params={"location_id": 1, "accessions": "NL-000001"},
        headers=auth_headers,
    )
    assert both.status_code == 422


def test_labels_unknown_accession_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/labels.pdf",
        params={"accessions": "NL-999999"},
        headers=auth_headers,
    )
    assert response.status_code == 404
