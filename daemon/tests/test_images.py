"""Coin image upload tests."""

from __future__ import annotations

import io
import re

import pytest

from fastapi.testclient import TestClient
from numislens_core import Ledger
from PIL import Image

from numislens_daemon.routers.coins import MAX_IMAGE_BYTES


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
    # Uploads are re-encoded on store (EXIF strip / downscale), so compare the
    # DECODED image, not raw bytes.
    served = Image.open(io.BytesIO(response.content))
    original = Image.open(io.BytesIO(png_bytes))
    assert (served.format, served.size) == ("PNG", original.size)


def test_image_reject_svg_content_type(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    # image/svg+xml passes a naive startswith("image/") check but is
    # scriptable; only jpeg/png/webp are allowed.
    acc = make_coin()
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("x.svg", svg, "image/svg+xml")},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "image/svg+xml" in response.json()["detail"]


def test_image_reject_mislabeled_payload(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    # Content type claims PNG but the payload is text: decode-validation wins.
    acc = make_coin()
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"reverse": ("x.png", b"definitely not a png", "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_image_oversize_413(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin()
    oversized = png_bytes + b"0" * (MAX_IMAGE_BYTES + 1)
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("big.png", oversized, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 413


def _jpeg_bytes(size: tuple[int, int], exif: bool = False) -> bytes:
    img = Image.new("RGB", size, (200, 180, 140))
    buf = io.BytesIO()
    if exif:
        metadata = Image.Exif()
        metadata[0x010F] = "TestCam"  # Make
        metadata[0x0110] = "Phone X"  # Model
        img.save(buf, format="JPEG", exif=metadata.tobytes())
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def test_exif_stripped_on_upload(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.jpg", _jpeg_bytes((64, 64), exif=True), "image/jpeg")},
        headers=auth_headers,
    )
    assert upload.status_code == 200
    content_hash = upload.json()["images"][0]["content_hash"]

    stored = client.get(
        f"/api/v1/coins/{acc}/images/{content_hash}", headers=auth_headers
    )
    exif = Image.open(io.BytesIO(stored.content)).getexif()
    assert exif.get(0x010F) is None  # Make gone => whole EXIF block dropped


def test_downscale_preserves_aspect(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"slab": ("s.jpg", _jpeg_bytes((2400, 1200)), "image/jpeg")},
        headers=auth_headers,
    )
    content_hash = upload.json()["images"][0]["content_hash"]

    stored = client.get(
        f"/api/v1/coins/{acc}/images/{content_hash}", headers=auth_headers
    )
    width, height = Image.open(io.BytesIO(stored.content)).size
    assert max(width, height) <= 1600
    assert width == 2 * height  # aspect preserved


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


def _oriented_bytes(fmt: str) -> bytes:
    """A 40x20 landscape frame tagged "rotate 90 to display" plus GPS, the
    way a phone held upright stores a portrait photo."""
    img = Image.new("RGB", (40, 20), (200, 180, 140))
    metadata = Image.Exif()
    metadata[0x0112] = 6  # Orientation: rotate 90 CW to display
    metadata[0x010F] = "TestCam"
    metadata[0x8825] = {1: "N", 2: (45.0, 30.0, 0.0), 3: "W", 4: (93.0, 15.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, format=fmt, exif=metadata)
    return buf.getvalue()


@pytest.mark.parametrize(
    "fmt,content_type",
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_exif_orientation_is_applied_before_metadata_is_stripped(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    fmt: str,
    content_type: str,
) -> None:
    """Dropping the orientation tag without applying it stores phone photos
    sideways. The pixels must be upright AND the metadata (GPS included) gone."""
    acc = make_coin()
    upload = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o", _oriented_bytes(fmt), content_type)},
        headers=auth_headers,
    )
    assert upload.status_code == 200
    content_hash = upload.json()["images"][0]["content_hash"]
    stored = client.get(
        f"/api/v1/coins/{acc}/images/{content_hash}", headers=auth_headers
    )
    out = Image.open(io.BytesIO(stored.content))
    assert out.size == (20, 40)  # rotated upright: portrait, not 40x20
    exif = out.getexif()
    assert dict(exif) == {}
    assert dict(exif.get_ifd(0x8825)) == {}
