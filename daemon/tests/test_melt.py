"""Melt and portfolio endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

SILVER_DOLLAR_MELT_CENTS = round(0.77344 * 6001)


def test_melt_update_monkeypatched(
    client: TestClient,
    auth_headers: dict[str, str],
    patch_spot,
) -> None:
    patch_spot()
    response = client.post("/api/v1/melt/update", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body["recorded"]) == {"XAG", "XAU", "XPT"}
    assert body["errors"] == {}


def test_portfolio_math_seeded(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    patch_spot,
) -> None:
    make_coin()
    patch_spot(gold_cents=6001, yahoo_cents=6001)
    client.post("/api/v1/melt/update", headers=auth_headers)

    response = client.get("/api/v1/portfolio/value", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["melt"]["by_metal"]["XAG"]["cents"] == SILVER_DOLLAR_MELT_CENTS
    assert body["melt"]["total_display"]


def test_melt_status(
    client: TestClient,
    auth_headers: dict[str, str],
    patch_spot,
) -> None:
    patch_spot()
    client.post("/api/v1/melt/update", headers=auth_headers)

    response = client.get("/api/v1/melt/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    xag = body["spots"]["XAG"]
    assert xag is not None
    assert set(xag) == {
        "price_usd_cents",
        "price_display",
        "source",
        "fetched_at",
    }
    assert xag["source"] == "gold-api"
    assert body["portfolio"]["total_display"]
