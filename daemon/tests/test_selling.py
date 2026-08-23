"""Sell-prep endpoint tests: listing kits and the listings CSV."""

from __future__ import annotations

import csv
import io
import json
import zipfile

from fastapi.testclient import TestClient


def _upload_photo(client, auth_headers, acc, png_bytes):
    response = client.post(
        f"/api/v1/coins/{acc}/images",
        files={"obverse": ("o.png", png_bytes, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_listing_kit_zip_contents(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    png_bytes: bytes,
) -> None:
    acc = make_coin({
        "series": "Washington Quarter", "year": 1932, "mintmark": "D",
        "grade_bucket": "G", "grade_source": "human",
        "value_est_cents": 12500, "value_basis": "numismatic",
        "notes": "from grandpa's box",
    })
    _upload_photo(client, auth_headers, acc, png_bytes)
    client.post(
        f"/api/v1/coins/{acc}/appraise",
        json={
            "appraised_by": "human",
            "value_cents": 12500,
            "source_url": "https://auctions.example/lot/42",
        },
        headers=auth_headers,
    )

    response = client.get(f"/api/v1/coins/{acc}/listing-kit.zip", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"numislens-listing-{acc}.zip" in response.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(zf.namelist())
    assert "listing.txt" in names
    assert "metadata.json" in names
    assert any(n.startswith("images/obverse-") for n in names)

    listing = zf.read("listing.txt").decode("utf-8")
    assert listing.startswith("1932D Washington Quarter")
    assert "Condition: Good." in listing  # human grade, no photo-grade hedge
    assert "grandpa's box" in listing
    assert "https://auctions.example/lot/42" in listing

    metadata = json.loads(zf.read("metadata.json"))
    assert metadata["coin"]["accession_no"] == acc
    assert metadata["appraisals"][0]["source_url"] == "https://auctions.example/lot/42"
    assert metadata["images"][0]["file"].startswith("images/obverse-")


def test_listing_kit_omits_absent_facts(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin({"series": None, "year": None, "denomination": None})  # bare
    response = client.get(f"/api/v1/coins/{acc}/listing-kit.zip", headers=auth_headers)
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    listing = zf.read("listing.txt").decode("utf-8")
    assert f"Coin {acc}" in listing  # fallback title, accession-anchored
    assert "Condition:" not in listing
    assert "Value:" not in listing


def test_listing_kit_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get(
        "/api/v1/coins/NL-999999/listing-kit.zip", headers=auth_headers
    )
    assert response.status_code == 404


def test_listings_csv_defaults_to_for_sale(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    for_sale = make_coin({"series": "Peace Dollar", "year": 1922})
    client.post(
        f"/api/v1/coins/{for_sale}/disposition",
        json={"disposition": "for_sale"},
        headers=auth_headers,
    )
    make_coin({"series": "Peace Dollar", "year": 1923})  # stays owned

    response = client.get("/api/v1/export/listings.csv", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [r["CustomLabel"] for r in rows] == [for_sale]
    assert rows[0]["Title"] == "1922P Peace Dollar"  # make_coin defaults mintmark P
    assert rows[0]["Format"] == "FixedPrice"

    # Explicit disposition override works too.
    owned = client.get(
        "/api/v1/export/listings.csv?disposition=owned", headers=auth_headers
    )
    owned_rows = list(csv.DictReader(io.StringIO(owned.text)))
    assert for_sale not in [r["CustomLabel"] for r in owned_rows]


def test_listings_csv_invalid_disposition_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/export/listings.csv?disposition=nope", headers=auth_headers
    )
    assert response.status_code == 422
