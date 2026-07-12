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


def test_coin_detail_includes_image_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    content_hash = upload.json()["images"][0]["content_hash"]

    detail = client.get(f"/api/v1/coins/{acc}", headers=auth_headers)
    assert detail.status_code == 200
    images = detail.json()["coin_images"]
    assert len(images) == 1
    assert images[0]["kind"] == "obverse"
    assert images[0]["content_hash"] == content_hash
    # The on-disk path must not leak to clients.
    assert "path" not in images[0]


def test_serve_image_bytes(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    content_hash = upload.json()["images"][0]["content_hash"]

    response = client.get(
        f"/api/v1/coins/{acc}/images/{content_hash}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.content == png_bytes


def test_serve_image_requires_auth(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    content_hash = upload.json()["images"][0]["content_hash"]
    response = client.get(f"/api/v1/coins/{acc}/images/{content_hash}")
    assert response.status_code == 401


def test_serve_image_unknown_hash_404(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    response = client.get(
        f"/api/v1/coins/{acc}/images/" + "0" * 64, headers=auth_headers
    )
    assert response.status_code == 404


def test_deep_link_serves_shell(
    client: TestClient,
) -> None:
    # /c/<accession> is a virtual PWA route; the daemon serves the SPA shell
    # (no auth — it is just the static index.html) and the client router
    # redirects to #/coin/<accession>.
    response = client.get("/c/NL-000002")
    assert response.status_code == 200
    assert "<title>NumisLens</title>" in response.text
    assert "/js/app.js" in response.text
