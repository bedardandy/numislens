from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from numislens_mcp.config import load_config
from numislens_mcp.server import (
    add_coin,
    add_location,
    album_import_status,
    albums_list,
    find_coins,
    get_coin,
    get_label_pdf,
    get_roll_labels_pdf,
    get_wantlist_pdf,
    get_watchlist,
    list_stale,
    locate_coin,
    melt_status,
    melt_update,
    move_coin,
    quick_add,
    roll_create,
    roll_get,
    roll_pull,
    rolls_list,
    set_gaps,
    set_needs,
    submit_digest,
    watch_status,
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


async def test_watch_status_passes_n_and_returns_snapshot() -> None:
    payload = {
        "stale_count": 2,
        "stale": [{"accession": "NL-000001", "reason": "silver moved", "since": "x"}],
        "watchlist": [{"accession_no": "NL-000009", "value_est_cents": 9000}],
        "delta": {"XAG": {"pct": 4.2}},
    }
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/watch/status").mock(
            return_value=Response(200, json=payload)
        )
        result = await watch_status(n=10)
        assert route.called
        assert route.calls.last.request.url.params["n"] == "10"
    parsed = json.loads(result)
    assert parsed["stale_count"] == 2
    assert parsed["watchlist"][0]["value_est_cents"] == 9000


async def test_list_stale_projects_stale_only() -> None:
    payload = {
        "stale_count": 1,
        "stale": [{"accession": "NL-000001", "reason": "digest", "since": "x"}],
        "watchlist": [{"accession_no": "NL-000009"}],
        "delta": {},
    }
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/watch/status").mock(return_value=Response(200, json=payload))
        result = await list_stale()
    parsed = json.loads(result)
    assert parsed["stale_count"] == 1
    assert "watchlist" not in parsed
    assert parsed["stale"][0]["reason"] == "digest"


async def test_get_watchlist_returns_array() -> None:
    payload = {
        "stale_count": 0,
        "stale": [],
        "watchlist": [{"accession_no": "NL-000009", "value_est_cents": 9000}],
        "delta": {},
    }
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/watch/status").mock(
            return_value=Response(200, json=payload)
        )
        result = await get_watchlist(n=5)
        assert route.calls.last.request.url.params["n"] == "5"
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert parsed[0]["value_est_cents"] == 9000


async def test_submit_digest_posts_items() -> None:
    items = [{"series": "Morgan Dollar", "reason": "silver rally"}]
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/watch/digest").mock(
            return_value=Response(
                200, json={"items": [{"series": "Morgan Dollar", "matched": 3}],
                           "total_marked": 3}
            )
        )
        result = await submit_digest(items)
        body = json.loads(route.calls.last.request.content)
        assert body == {"items": items}
    assert json.loads(result)["total_marked"] == 3


async def test_submit_digest_unknown_series_relays_422() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.post("/api/v1/watch/digest").mock(
            return_value=Response(
                422,
                json={"detail": {"message": "unknown series 'X'",
                                 "known_series": ["Morgan Dollar"]}},
            )
        )
        result = await submit_digest([{"series": "X", "reason": "y"}])
    assert result.startswith("Error: API error 422:")


async def test_identify_coin_returns_result_verbatim(monkeypatch) -> None:
    from numislens_vision import pipeline

    from numislens_mcp.server import identify_coin

    canned = {
        "accession": "NL-000001",
        "accepted": {"series": "Peace Dollar", "year": 1921, "mintmark": None,
                     "grade_bucket": "XF", "grade_confidence": "photo-grade"},
        "escalations": [{"field": "mintmark",
                         "readings": {"ocr": "D", "vlm": "NONE"}, "note": "disagree"}],
        "tiers_used": ["ocr:x", "vlm:y"],
        "tiers_unavailable": ["gemma: not configured"],
    }
    monkeypatch.setattr(pipeline, "identify", lambda cfg, acc: canned)
    out = identify_coin("NL-000001")
    parsed = json.loads(out)
    assert parsed == canned
    # Escalations survive verbatim for the assistant to adjudicate.
    assert parsed["escalations"][0]["field"] == "mintmark"


async def test_identify_coin_reports_error(monkeypatch) -> None:
    from numislens_vision import pipeline

    from numislens_mcp.server import identify_coin

    def boom(cfg, acc):
        raise RuntimeError("cannot reach the NumisLens daemon")

    monkeypatch.setattr(pipeline, "identify", boom)
    out = identify_coin("NL-000001")
    assert out.startswith("Error: cannot reach the NumisLens daemon")


# ---------------------------------------------------------------------------
# Rolls
# ---------------------------------------------------------------------------

async def test_rolls_list_passes_status() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/rolls").mock(
            return_value=Response(200, json=[{"roll_no": "NR-000001", "status": "unopened"}])
        )
        out = await rolls_list(status="unopened")
        assert route.called
        assert route.calls.last.request.url.params["status"] == "unopened"
    assert json.loads(out)[0]["roll_no"] == "NR-000001"


async def test_rolls_list_no_status_omits_param() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/rolls").mock(return_value=Response(200, json=[]))
        await rolls_list()
        assert "status" not in route.calls.last.request.url.params


async def test_roll_get_roundtrip() -> None:
    roll = {"roll_no": "NR-000001", "denomination": "cent", "count": 50, "best_cents": 5000}
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/rolls/NR-000001").mock(return_value=Response(200, json=roll))
        result = await roll_get("NR-000001")
    assert json.loads(result)["best_cents"] == 5000


async def test_roll_get_404_message() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/rolls/NR-999999").mock(
            return_value=Response(404, json={"detail": "roll not found: NR-999999"})
        )
        result = await roll_get("NR-999999")
    assert result == "Error: API error 404: roll not found: NR-999999"


async def test_roll_create_sends_body() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/rolls").mock(
            return_value=Response(201, json={"roll_no": "NR-000001"})
        )
        await roll_create(
            denomination="cent",
            count=50,
            composition_name="Copper (95%)",
            cost_basis_cents=500,
        )
        body = json.loads(route.calls.last.request.content)
        assert body == {
            "denomination": "cent",
            "count": 50,
            "composition_name": "Copper (95%)",
            "cost_basis_cents": 500,
        }


async def test_roll_create_422_relays_detail() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.post("/api/v1/rolls").mock(
            return_value=Response(422, json={"detail": "unknown composition: 'x'"})
        )
        result = await roll_create(denomination="cent", count=50, composition_name="x")
    assert result == "Error: API error 422: unknown composition: 'x'"


async def test_roll_pull_sends_count_and_quick() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/rolls/NR-000001/pull").mock(
            return_value=Response(
                200,
                json={
                    "roll": {"roll_no": "NR-000001", "count": 48},
                    "coins_created": ["NL-000010", "NL-000011"],
                },
            )
        )
        result = await roll_pull("NR-000001", 2, quick=["1943 steel cent", "1955 D cent"])
        body = json.loads(route.calls.last.request.content)
        assert body == {"count": 2, "quick": ["1943 steel cent", "1955 D cent"]}
    parsed = json.loads(result)
    assert parsed["coins_created"] == ["NL-000010", "NL-000011"]


async def test_roll_pull_without_quick_omits_key() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/rolls/NR-000001/pull").mock(
            return_value=Response(
                200, json={"roll": {"roll_no": "NR-000001"}, "coins_created": []}
            )
        )
        await roll_pull("NR-000001", 3)
        body = json.loads(route.calls.last.request.content)
        assert body == {"count": 3}


async def test_roll_pull_422_relays_unparseable_detail() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.post("/api/v1/rolls/NR-000001/pull").mock(
            return_value=Response(
                422,
                json={"detail": {"message": "could not identify a coin from quick text"}},
            )
        )
        result = await roll_pull("NR-000001", 1, quick=["asdf qwerty"])
    assert result.startswith("Error: API error 422:")


async def test_get_roll_labels_pdf_writes_file(tmp_path) -> None:
    pdf_bytes = b"%PDF-1.4 roll labels"
    out_file = tmp_path / "roll-labels.pdf"
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/labels/rolls.pdf").mock(
            return_value=Response(200, content=pdf_bytes)
        )
        result = await get_roll_labels_pdf(output_path=str(out_file), roll_nos=["NR-000001"])
        assert route.calls.last.request.url.params.get_list("rolls") == ["NR-000001"]
    assert out_file.exists()
    assert out_file.read_bytes() == pdf_bytes
    assert result.startswith("Saved roll label PDF to")


async def test_get_roll_labels_pdf_no_selection_omits_param(tmp_path) -> None:
    out_file = tmp_path / "roll-labels.pdf"
    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/labels/rolls.pdf").mock(
            return_value=Response(200, content=b"%PDF-1.4")
        )
        await get_roll_labels_pdf(output_path=str(out_file))
        assert "rolls" not in route.calls.last.request.url.params


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------

async def test_albums_list_returns_imports() -> None:
    payload = [{"id": 1, "name": "Lincoln folder", "status": "analyzed", "page_count": 3}]
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/albums/imports").mock(return_value=Response(200, json=payload))
        result = await albums_list()
    assert json.loads(result)[0]["status"] == "analyzed"


async def test_album_import_status_returns_merged_slots_and_candidates() -> None:
    payload = {
        "id": 1,
        "name": "Lincoln folder",
        "status": "analyzed",
        "pages": [],
        "merged_slots": [{"year": 1914, "mint": "D", "fill_state": "uncertain"}],
        "match_candidates": [{"manifest_id": "lincoln-cents", "score": 0.9}],
    }
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/albums/imports/1").mock(return_value=Response(200, json=payload))
        result = await album_import_status(1)
    parsed = json.loads(result)
    assert parsed["merged_slots"][0]["fill_state"] == "uncertain"
    assert parsed["match_candidates"][0]["manifest_id"] == "lincoln-cents"


async def test_album_import_status_404_message() -> None:
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/albums/imports/99").mock(
            return_value=Response(404, json={"detail": "album import not found: 99"})
        )
        result = await album_import_status(99)
    assert result == "Error: API error 404: album import not found: 99"


# ---------------------------------------------------------------------------
# Set needs / want list
# ---------------------------------------------------------------------------

async def test_set_needs_returns_missing_and_completion() -> None:
    payload = {
        "set_key": "lincoln-cents",
        "name": "Lincoln Cents",
        "total_slots": 100,
        "filled": 40,
        "completion_pct": 40.0,
        "missing": [{"year": 1931, "mint": "S", "note": "", "key_date": True}],
        "key_dates_missing": 1,
    }
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/sets/lincoln-cents/needs").mock(return_value=Response(200, json=payload))
        result = await set_needs("lincoln-cents")
    parsed = json.loads(result)
    assert parsed["completion_pct"] == 40.0
    assert parsed["missing"][0]["key_date"] is True


async def test_get_wantlist_pdf_writes_file(tmp_path) -> None:
    pdf_bytes = b"%PDF-1.4 wantlist"
    out_file = tmp_path / "wantlist.pdf"
    with respx.mock(base_url="http://testserver") as mock:
        mock.get("/api/v1/sets/lincoln-cents/wantlist.pdf").mock(
            return_value=Response(200, content=pdf_bytes)
        )
        result = await get_wantlist_pdf(output_path=str(out_file), set_id="lincoln-cents")
    assert out_file.exists()
    assert out_file.read_bytes() == pdf_bytes
    assert result.startswith("Saved want-list PDF to")


async def test_edit_coin_sends_only_provided_fields() -> None:
    from numislens_mcp.server import edit_coin

    with respx.mock(base_url="http://testserver") as mock:
        route = mock.put("/api/v1/coins/NL-000001").mock(
            return_value=Response(200, json={"changed": {"year": [1921, 1922]}})
        )
        out = await edit_coin("NL-000001", year=1922, notes="corrected")
        assert "changed" in json.loads(out)
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"year": 1922, "notes": "corrected"}


async def test_edit_coin_empty_body_is_a_local_error() -> None:
    from numislens_mcp.server import edit_coin

    with respx.mock(base_url="http://testserver", assert_all_called=False) as mock:
        mock.put("/api/v1/coins/NL-000001").mock(return_value=Response(200, json={}))
        out = await edit_coin("NL-000001")
        assert out.startswith("Error:")
        assert not any(r.called for r in mock.routes)


async def test_edit_coin_rejects_grade_via_api_error_path() -> None:
    # Grade is not an edit_coin parameter at all (invariant 2); the daemon
    # schema would also reject it — here we just prove the error path formats.
    from numislens_mcp.server import edit_coin

    with respx.mock(base_url="http://testserver") as mock:
        route = mock.put("/api/v1/coins/NL-000001").mock(
            return_value=Response(422, json={"detail": "not editable fields"})
        )
        out = await edit_coin("NL-000001", year=1900)
        assert "Error:" in out
        assert route.called


async def test_set_disposition_sold_requires_price_field() -> None:
    from numislens_mcp.server import set_disposition

    with respx.mock(base_url="http://testserver") as mock:
        route = mock.post("/api/v1/coins/NL-000001/disposition").mock(
            return_value=Response(200, json={"disposition": "sold"})
        )
        await set_disposition(
            "NL-000001",
            disposition="sold",
            sold_price_cents=12500,
            sold_date="2026-08-22",
        )
        sent = json.loads(route.calls.last.request.content)
        assert sent == {
            "disposition": "sold",
            "sold_date": "2026-08-22",
            "sold_price_cents": 12500,
        }


async def test_find_duplicates_returns_groups() -> None:
    from numislens_mcp.server import find_duplicates

    with respx.mock(base_url="http://testserver") as mock:
        route = mock.get("/api/v1/duplicates").mock(
            return_value=Response(
                200,
                json=[{"series": "Peace Dollar", "year": 1922, "count": 2}],
            )
        )
        out = await find_duplicates()
        data = json.loads(out)
        assert data[0]["count"] == 2
        assert route.called
