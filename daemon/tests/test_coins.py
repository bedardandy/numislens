"""Coin endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from numislens_core import Ledger


def test_create_and_get_coin(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    response = client.get(f"/api/v1/coins/{acc}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["accession_no"] == acc
    assert body["cost_basis_display"] == "$50.00"


def test_create_returns_display_strings(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/coins",
        json={"value_est_cents": 3500},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["value_est_display"] == "$35.00"


def test_find_by_series(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    make_coin()
    make_coin()
    peace = client.get(
        "/api/v1/coins",
        params={"series": "Peace Dollar"},
        headers=auth_headers,
    )
    assert peace.status_code == 200
    assert len(peace.json()) >= 2

    none_series = client.get(
        "/api/v1/coins",
        params={"series": "Nonexistent"},
        headers=auth_headers,
    )
    assert none_series.status_code == 200
    assert none_series.json() == []


def test_list_compositions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/compositions", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body
    expected_keys = {"id", "name", "metal", "fineness", "precious_weight_ozt"}
    for item in body:
        assert set(item.keys()) == expected_keys

    unauth = client.get("/api/v1/compositions")
    assert unauth.status_code == 401


def test_get_unknown_coin_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/coins/NL-999999", headers=auth_headers)
    assert response.status_code == 404


def test_move_records_event(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
    db_path,
) -> None:
    acc = make_coin()
    loc = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "B1"},
        headers=auth_headers,
    )
    assert loc.status_code == 200
    location_id = loc.json()["id"]

    move = client.post(
        f"/api/v1/coins/{acc}/move",
        json={"location_id": location_id},
        headers=auth_headers,
    )
    assert move.status_code == 200
    assert move.json()["location_id"] == location_id

    ldb = Ledger(str(db_path))
    try:
        coin_id = ldb.conn.execute(
            "SELECT id FROM coins WHERE accession_no = ?", (acc,)
        ).fetchone()[0]
        rows = ldb.conn.execute(
            "SELECT event_type FROM events WHERE coin_id = ? AND event_type = 'moved'",
            (coin_id,),
        ).fetchall()
        assert len(rows) >= 1
    finally:
        ldb.close()


def test_appraise_updates_value(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    acc = make_coin()
    response = client.post(
        f"/api/v1/coins/{acc}/appraise",
        json={
            "appraised_by": "human",
            "grade_bucket": "XF",
            "value_cents": 9900,
            "value_basis": "numismatic",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["appraisal_id"]
    assert body["coin"]["value_est_cents"] == 9900


def test_move_unknown_coin_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/coins/NL-999999/move",
        json={"location_id": 1},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_move_conflict_409(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    loc_a = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "A"},
        headers=auth_headers,
    )
    assert loc_a.status_code == 200
    location_a = loc_a.json()["id"]

    loc_b = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "B"},
        headers=auth_headers,
    )
    assert loc_b.status_code == 200
    location_b = loc_b.json()["id"]

    acc = make_coin({"location_id": location_a})

    move = client.post(
        f"/api/v1/coins/{acc}/move",
        json={"location_id": location_b, "expected_from_location_id": location_b},
        headers=auth_headers,
    )
    assert move.status_code == 409
    assert "move conflict" in move.json()["detail"]

    coin = client.get(f"/api/v1/coins/{acc}", headers=auth_headers)
    assert coin.status_code == 200
    assert coin.json()["location_id"] == location_a


def test_move_with_correct_expected_from_200(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    loc_a = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "A"},
        headers=auth_headers,
    )
    assert loc_a.status_code == 200
    location_a = loc_a.json()["id"]

    loc_b = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "B"},
        headers=auth_headers,
    )
    assert loc_b.status_code == 200
    location_b = loc_b.json()["id"]

    acc = make_coin({"location_id": location_a})

    move = client.post(
        f"/api/v1/coins/{acc}/move",
        json={"location_id": location_b, "expected_from_location_id": location_a},
        headers=auth_headers,
    )
    assert move.status_code == 200
    assert move.json()["location_id"] == location_b


def test_move_without_expected_from_200(
    client: TestClient,
    auth_headers: dict[str, str],
    make_coin,
) -> None:
    loc_a = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "A"},
        headers=auth_headers,
    )
    assert loc_a.status_code == 200
    location_a = loc_a.json()["id"]

    loc_b = client.post(
        "/api/v1/locations",
        json={"kind": "box", "label": "B"},
        headers=auth_headers,
    )
    assert loc_b.status_code == 200
    location_b = loc_b.json()["id"]

    acc = make_coin({"location_id": location_a})

    move = client.post(
        f"/api/v1/coins/{acc}/move",
        json={"location_id": location_b},
        headers=auth_headers,
    )
    assert move.status_code == 200
    assert move.json()["location_id"] == location_b


# --- Phase 4: PATCH /coins/{accession} vision writeback --------------------


def test_patch_fills_null_and_reports_skips(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/coins", json={"year": 1943}, headers=auth_headers
    )
    acc = created.json()["accession_no"]
    resp = client.patch(
        f"/api/v1/coins/{acc}",
        json={"series": "Lincoln Wheat Cent", "year": 1949, "mintmark": "D"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["written"] == {"series": "Lincoln Wheat Cent", "mintmark": "D"}
    assert body["skipped"] == {"year": 1943}
    assert body["coin"]["series"] == "Lincoln Wheat Cent"
    assert body["coin"]["year"] == 1943


def test_patch_unknown_coin_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/api/v1/coins/NL-999999", json={"series": "x"}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_patch_invalid_grade_source_422(
    client: TestClient, auth_headers: dict[str, str], make_coin
) -> None:
    acc = make_coin({"grade_bucket": None})
    resp = client.patch(
        f"/api/v1/coins/{acc}",
        json={"grade_bucket": "XF", "grade_source": "bogus"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_patch_unknown_field_422(
    client: TestClient, auth_headers: dict[str, str], make_coin
) -> None:
    acc = make_coin()
    resp = client.patch(
        f"/api/v1/coins/{acc}",
        json={"value_est_cents": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_coin_includes_appraisals(
    client: TestClient, auth_headers: dict[str, str], make_coin
) -> None:
    acc = make_coin()
    client.post(
        f"/api/v1/coins/{acc}/appraise",
        json={"appraised_by": "vision:cross-vote", "grade_bucket": "XF"},
        headers=auth_headers,
    )
    body = client.get(f"/api/v1/coins/{acc}", headers=auth_headers).json()
    assert "appraisals" in body
    assert body["appraisals"][0]["appraised_by"] == "vision:cross-vote"
