"""Appraisal-report endpoint tests (JSON rollup + printable PDF)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _comp_id(client: TestClient, auth_headers: dict[str, str], name: str) -> int:
    resp = client.get("/api/v1/compositions", headers=auth_headers)
    assert resp.status_code == 200
    for comp in resp.json():
        if comp["name"] == name:
            return comp["id"]
    raise AssertionError(f"composition not found: {name}")


def _make(client, auth_headers, **fields) -> str:
    resp = client.post("/api/v1/coins", json=fields, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["accession_no"]


def _seed_four(client, auth_headers, patch_spot) -> dict[str, str]:
    """One coin per bucket: melt-silver, collectible, face-clad, unvalued."""
    silver = _comp_id(client, auth_headers, "90% silver dollar")
    clad = _comp_id(client, auth_headers, "Cupronickel clad")

    # Primary-source spot rows (source == PRIMARY_SOURCE 'gold-api').
    patch_spot(gold_cents=6001, yahoo_cents=6001)
    accs = {
        # melt wins: silver composition + spot, no numismatic premium.
        "melt": _make(
            client, auth_headers, composition_id=silver, denomination="dollar", value_basis="melt"
        ),
        # collectible wins: large numismatic estimate.
        "collectible": _make(
            client,
            auth_headers,
            composition_id=silver,
            denomination="dollar",
            value_basis="numismatic",
            value_est_cents=500000,
        ),
        # face only: clad quarter, US, no estimate.
        "face": _make(client, auth_headers, composition_id=clad, denomination="quarter"),
        # unvalued: no composition, no denomination, no estimate.
        "unvalued": _make(client, auth_headers, notes="mystery token"),
    }
    resp = client.post("/api/v1/melt/update", headers=auth_headers)
    assert resp.status_code == 200
    return accs


# --- auth --------------------------------------------------------------------


def test_report_json_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/report/appraisal").status_code == 401


def test_report_pdf_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/report/appraisal.pdf").status_code == 401


def test_report_wrong_token_rejected(client: TestClient) -> None:
    bad = {"Authorization": "Bearer wrong-token"}
    assert client.get("/api/v1/report/appraisal", headers=bad).status_code == 401
    assert client.get("/api/v1/report/appraisal.pdf", headers=bad).status_code == 401


# --- JSON shape --------------------------------------------------------------


def test_report_json_shape_seeded(client, auth_headers, patch_spot) -> None:
    _seed_four(client, auth_headers, patch_spot)

    resp = client.get("/api/v1/report/appraisal", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    bd = body["breakdown"]
    assert bd["collectible"]["count"] == 1
    assert bd["melt"]["count"] == 1
    assert bd["face"]["count"] == 1
    assert bd["unvalued"]["count"] == 1

    # highlights ordered best-value descending; collectible (500000c) leads.
    values = [h["best_cents"] for h in body["highlights"]]
    assert values == sorted(values, reverse=True)
    assert body["highlights"][0]["best_basis"] == "collectible"
    assert body["highlights"][0]["best_cents"] == 500000

    # groups present, spot provenance present (primary-source XAG). Subset (not
    # ==) so additive group keys (rolls, albums, ...) from concurrent
    # workstreams don't fight over an exact key-set assertion.
    assert {"sets", "mints", "series", "metals"} <= set(body["groups"])
    assert "rolls" in body["groups"]
    assert "XAG" in body["spot"]
    assert body["spot"]["XAG"]["source"] == "gold-api"

    # money stays integer cents in JSON (PWA formats client-side).
    assert isinstance(body["totals"]["best_total_cents"], int)


def test_report_top_param_truncates(client, auth_headers, patch_spot) -> None:
    _seed_four(client, auth_headers, patch_spot)

    resp = client.get("/api/v1/report/appraisal", params={"top": 1}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["top_n"] == 1
    assert len(body["highlights"]) == 1


def test_report_top_out_of_range_422(client, auth_headers) -> None:
    assert client.get(
        "/api/v1/report/appraisal", params={"top": 0}, headers=auth_headers
    ).status_code == 422
    assert client.get(
        "/api/v1/report/appraisal", params={"top": 101}, headers=auth_headers
    ).status_code == 422
    assert client.get(
        "/api/v1/report/appraisal", params={"top": "banana"}, headers=auth_headers
    ).status_code == 422


# --- PDF ---------------------------------------------------------------------


def test_report_pdf_seeded(client, auth_headers, patch_spot) -> None:
    _seed_four(client, auth_headers, patch_spot)

    json_resp = client.get("/api/v1/report/appraisal", headers=auth_headers)
    date = json_resp.json()["generated_at"][:10]

    resp = client.get("/api/v1/report/appraisal.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    disp = resp.headers["content-disposition"]
    assert "attachment" in disp
    assert f"numislens-appraisal-{date}.pdf" in disp


def test_report_pdf_empty_db_valid(client, auth_headers) -> None:
    resp = client.get("/api/v1/report/appraisal.pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_report_json_empty_db_zeroed(client, auth_headers) -> None:
    resp = client.get("/api/v1/report/appraisal", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["coin_count"] == 0
    assert body["totals"]["best_total_cents"] == 0
    assert body["totals"]["gain_loss_cents"] == 0
    assert body["highlights"] == []
    assert body["spot"] == {}


def test_worklist_endpoint_flags_key_dates(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    make_coin({
        "series": "Washington Quarter", "year": 1932, "mintmark": "D",
        "denomination": "quarter",
    })
    response = client.get("/api/v1/worklist?top=10", headers=auth_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["identity"] == "Washington Quarter 1932D"
    assert items[0]["potential_cents"] == 350000


def test_appraisal_report_includes_reference_provenance(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/report/appraisal", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["references"], list)
    assert any(s["id"] == "lincoln-wheat-cents" for s in body["references"])
    assert "worklist" in body
