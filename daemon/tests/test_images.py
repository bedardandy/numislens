"""Coin image upload tests."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from numislens_core import Ledger


def test_image_upload_roundtrip(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin()
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    images = response.json()["images"]
    assert len(images) == 1
    record = images[0]
    assert record["kind"] == "obverse"
    assert re.fullmatch(r"[0-9a-f]{64}", record["content_hash"])


def test_image_dedup(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
    db_path,
) -> None:
    acc = make_coin()
    for _ in range(2):
        response = client.post(
            f"/api/v1/coins/{acc}/images",
            files={"obverse": ("o.png", png_bytes, "image/png")},
            headers=auth_headers,
        )
        assert response.status_code == 200

    ldb = Ledger(str(db_path))
    try:
        assert len(ldb.list_images(acc)) == 1
    finally:
        ldb.close()


def test_image_reject_non_image(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("x.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_image_unknown_coin_404(
    client: TestClient,
    auth_headers: dict[str, str],
    png_bytes: bytes,
) -> None:
    response = client.post(
        "/api/v1/coins/NL-999999/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 404
