from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from numislens_mcp.config import load_config
from numislens_mcp.server import (
    add_coin,
    add_location,
    find_coins,
    get_coin,
    get_label_pdf,
    locate_coin,
    melt_status,
    melt_update,
    move_coin,
    quick_add,
    set_gaps,
)


@pytest.fixture(autouse=True)
def numislens_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUMISLENS_URL", "http://testserver")
    monkeypatch.setenv("NUMISLENS_TOKEN", "testtoken")


async def test_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUMISLENS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="NUMISLENS_TOKEN is not set"):
        load_config()


async def test_find_coins_passes_filters() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/coins").mock(
            return_value=Response(200, json=[{"accession_no": "NL-000001"}])
        )
        out = await find_coins(series="Peace Dollar", year=1921, mintmark="D")
        assert route.called
        sent = route.calls.last.request
        assert sent.headers["Authorization"] == "Bearer testtoken"
        assert sent.url.params["series"] == "Peace Dollar"
        assert sent.url.params["year"] == "1921"
        assert sent.url.params["mintmark"] == "D"
        assert "mint" not in sent.url.params
        assert json.loads(out)[0]["accession_no"] == "NL-000001"


async def test_get_coin_roundtrip() -> None:
    coin = {
        "accession_no": "NL-000001",
        "value_est_cents": 12345,
        "value_est_display": "$123.45",
    }
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/coins/NL-000001").mock(return_value=Response(200, json=coin))
        result = await get_coin("NL-000001")
    parsed = json.loads(result)
    assert parsed["value_est_cents"] == 12345
    assert parsed["value_est_display"] == "$123.45"


async def test_add_coin_sends_cents_body() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/coins").mock(
            return_value=Response(200, json={"accession_no": "NL-000002"})
        )
        await add_coin(
            series="Lincoln Cent",
            year=1943,
            mintmark="P",
            cost_basis_cents=400,
            value_est_cents=250,
        )
        body = json.loads(route.calls.last.request.content)
        assert body == {
            "series": "Lincoln Cent",
            "year": 1943,
            "mintmark": "P",
            "cost_basis_cents": 400,
            "value_est_cents": 250,
        }


async def test_add_coin_404_or_422_verbatim() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.post("/api/v1/coins").mock(
            return_value=Response(422, json={"detail": "unexpected keyword argument"})
        )
        result = await add_coin(series="x")
    assert result == "Error: API error 422: unexpected keyword argument"


async def test_get_coin_404_message() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/coins/NL-999").mock(
            return_value=Response(404, json={"detail": "coin not found: NL-999"})
        )
        result = await get_coin("NL-999")
    assert result == "Error: API error 404: coin not found: NL-999"


async def test_unauthorized_maps_to_token_hint() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/coins").mock(
            return_value=Response(401, json={"detail": "invalid token"})
        )
        result = await find_coins()
    assert result == (
        "Error: Unauthorized (401): check NUMISLENS_TOKEN matches the daemon bearer token."
    )


async def test_move_coin_body() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/coins/NL-1/move").mock(
            return_value=Response(200, json={"accession_no": "NL-1", "location_id": 7})
        )
        await move_coin("NL-1", 7)
        body = json.loads(route.calls.last.request.content)
        assert body == {"location_id": 7}


async def test_locate_coin_returns_path() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/coins/NL-1").mock(
            return_value=Response(
                200,
                json={"accession_no": "NL-1", "location_id": 3},
            )
        )
        mock.get("/api/v1/locations/3").mock(
            return_value=Response(
                200,
                json={
                    "id": 3,
                    "path": "Cabinet A > Box B2 > Slot 14",
                    "contents": [],
                },
            )
        )
        result = await locate_coin("NL-1")
    assert result == "Cabinet A > Box B2 > Slot 14"


async def test_locate_coin_no_location() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/coins/NL-2").mock(
            return_value=Response(200, json={"accession_no": "NL-2", "location_id": None})
        )
        result = await locate_coin("NL-2")
    assert result == "NL-2 has no location on record."


async def test_melt_status_reads_display() -> None:
    payload = {
        "portfolio": {
            "total_cents": 1000000,
            "total_display": "$10,000.00",
        }
    }
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/melt/status").mock(return_value=Response(200, json=payload))
        result = await melt_status()
    parsed = json.loads(result)
    assert parsed["portfolio"]["total_cents"] == 1000000
    assert parsed["portfolio"]["total_display"] == "$10,000.00"


async def test_add_location_body() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/locations").mock(
            return_value=Response(200, json={"id": 5, "path": "Cabinet A"})
        )
        result = await add_location(kind="cabinet", label="Cabinet A")
        body = json.loads(route.calls.last.request.content)
        assert body == {"kind": "cabinet", "label": "Cabinet A"}
        assert json.loads(result)["id"] == 5


async def test_set_gaps_accepts_key() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/sets/washington-quarters/gaps").mock(
            return_value=Response(200, json={"gaps": [{"year": 1932, "mint": "D"}]})
        )
        result = await set_gaps("washington-quarters")
    assert json.loads(result)["gaps"][0]["year"] == 1932


async def test_get_label_pdf_writes_file(tmp_path) -> None:
    pdf_bytes = b"%PDF-1.4 fake"
    out_file = tmp_path / "labels.pdf"
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/labels.pdf").mock(return_value=Response(200, content=pdf_bytes))
        result = await get_label_pdf(output_path=str(out_file), location_id=2)
    assert out_file.exists()
    assert out_file.read_bytes() == pdf_bytes
    assert result.startswith("Saved label PDF to")


async def test_get_label_pdf_requires_exactly_one() -> None:
    result = await get_label_pdf(output_path="/tmp/x.pdf")
    assert result == "Error: provide exactly one of location_id or accessions"


async def test_quick_add_posts_text_and_relays_unresolved() -> None:
    payload = {
        "parsed": {"year": 1943, "series": "Lincoln Wheat Cent"},
        "unresolved": ["box 9", 'unrecognized: "shiny"'],
        "created": "NL-000007",
        "coin": {"accession_no": "NL-000007"},
    }
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/coins/quick").mock(
            return_value=Response(200, json=payload)
        )
        result = await quick_add("1943 shiny steel cent, box 9")
        assert route.called
        body = json.loads(route.calls.last.request.content)
        assert body == {"text": "1943 shiny steel cent, box 9"}
    parsed = json.loads(result)
    assert parsed["created"] == "NL-000007"
    # Both flavors survive verbatim for the model to relay: the unmapped
    # location AND the unrecognized-leftover-text entry.
    assert parsed["unresolved"] == ["box 9", 'unrecognized: "shiny"']


async def test_quick_add_422_relays_detail() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.post("/api/v1/coins/quick").mock(
            return_value=Response(
                422,
                json={"detail": "could not identify a coin: need a series or a year"},
            )
        )
        result = await quick_add("asdf qwerty")
    assert result.startswith("Error: API error 422:")


async def test_melt_update_posts() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/melt/update").mock(
            return_value=Response(200, json={"recorded": ["silver"], "updated": 3})
        )
        result = await melt_update()
        assert route.called
        assert json.loads(result)["updated"] == 3
