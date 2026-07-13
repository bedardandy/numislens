"""Album import lifecycle + want-list endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_import(client, auth_headers, name="Test Album") -> int:
    r = client.post("/api/v1/albums/imports", json={"name": name}, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    return body["import_id"]


def _upload_page(client, auth_headers, import_id, data, filename="p.png") -> int:
    r = client.post(
        f"/api/v1/albums/imports/{import_id}/pages",
        files=[("pages", (filename, data, "image/png"))],
        headers=auth_headers,
    )
    assert r.status_code == 200
    added = r.json()["added"]
    assert len(added) == 1
    return added[0]["page_id"]


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

def test_albums_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/albums/imports").status_code == 401
    assert client.post("/api/v1/albums/imports", json={}).status_code == 401


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

def test_import_create_and_list(client: TestClient, auth_headers) -> None:
    imp = _create_import(client, auth_headers, name="Grandpa's folder")
    listing = client.get("/api/v1/albums/imports", headers=auth_headers).json()
    match = next(i for i in listing if i["id"] == imp)
    assert match["name"] == "Grandpa's folder"
    assert match["status"] == "pending"
    assert match["page_count"] == 0


def test_upload_pages_and_dedup(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    other = png_bytes + b"variant"
    # First request: two distinct pages.
    r = client.post(
        f"/api/v1/albums/imports/{imp}/pages",
        files=[
            ("pages", ("a.png", png_bytes, "image/png")),
            ("pages", ("b.png", other, "image/png")),
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["added"]) == 2
    assert r.json()["duplicates"] == []

    # Re-upload the first: skipped as a duplicate hash.
    r2 = client.post(
        f"/api/v1/albums/imports/{imp}/pages",
        files=[("pages", ("a-again.png", png_bytes, "image/png"))],
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["added"] == []
    assert len(r2.json()["duplicates"]) == 1


def test_page_image_roundtrip(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    r = client.get(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/image", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.content == png_bytes


def test_analysis_server_side_parse(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    # Analyzer supplies label text + fill state only; server parses year/mint.
    # Includes a two-digit label resolvable only via the page-title century hint.
    r = client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json={
            "page_title": "LINCOLN CENTS 1941-1958",
            "page_type": "page",
            "slots": [
                {"slot_index": 0, "label_text": "1943 D", "fill_state": "filled"},
                {"slot_index": 1, "label_text": "58 D", "fill_state": "empty"},
                {"slot_index": 2, "label_text": "smudge", "fill_state": "uncertain"},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    slots = {s["slot_index"]: s for s in r.json()["slots"]}
    assert slots[0]["year"] == 1943 and slots[0]["mint"] == "D"
    assert slots[1]["year"] == 1958 and slots[1]["mint"] == "D"  # 2-digit via hint
    assert slots[2]["year"] is None  # unparseable, not fabricated

    # Import flipped to analyzed.
    detail = client.get(f"/api/v1/albums/imports/{imp}", headers=auth_headers).json()
    assert detail["status"] == "analyzed"
    assert detail["match_candidates"]  # candidates recomputed live


def test_analysis_is_idempotent(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    body = {
        "page_title": None,
        "page_type": "page",
        "slots": [{"slot_index": 0, "label_text": "1909 P", "fill_state": "filled"}],
    }
    client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json=body,
        headers=auth_headers,
    )
    r2 = client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json=body,
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert len(r2.json()["slots"]) == 1  # replaced, not duplicated


def test_human_patch_slot(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    posted = client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json={
            "page_title": None,
            "page_type": "page",
            "slots": [{"slot_index": 0, "label_text": "1914 D", "fill_state": "uncertain"}],
        },
        headers=auth_headers,
    ).json()
    slot_id = posted["slots"][0]["slot_id"]
    r = client.patch(
        f"/api/v1/albums/imports/{imp}/slots/{slot_id}",
        json={"fill_state": "filled"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["fill_state"] == "filled"
    assert r.json()["source"] == "human"

    # cross-import ownership: another import cannot touch this slot.
    other = _create_import(client, auth_headers)
    bad = client.patch(
        f"/api/v1/albums/imports/{other}/slots/{slot_id}",
        json={"fill_state": "empty"},
        headers=auth_headers,
    )
    assert bad.status_code == 404


def _seed_committable(client, auth_headers, png_bytes, *, uncertain=False):
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    slots = [
        {"slot_index": 0, "label_text": "1909 P", "fill_state": "filled"},
        {"slot_index": 1, "label_text": "1909 S", "fill_state": "filled"},
    ]
    if uncertain:
        slots.append(
            {"slot_index": 2, "label_text": "1914 D", "fill_state": "uncertain"}
        )
    client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json={"page_title": "LINCOLN CENTS", "page_type": "page", "slots": slots},
        headers=auth_headers,
    )
    return imp


def test_commit_blocks_uncertain_then_policy_empty(
    client: TestClient, auth_headers, png_bytes
) -> None:
    imp = _seed_committable(client, auth_headers, png_bytes, uncertain=True)

    blocked = client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"manifest_id": "lincoln-wheat-1909-1958"},
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    ok = client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"manifest_id": "lincoln-wheat-1909-1958", "uncertain_policy": "empty"},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    summary = ok.json()
    assert summary["set_key"] == "lincoln-wheat-1909-1958"
    assert summary["filled"] == 2
    assert summary["treated_uncertain_as_empty"] == 1


def test_commit_then_needs_and_wantlist(
    client: TestClient, auth_headers, png_bytes
) -> None:
    imp = _seed_committable(client, auth_headers, png_bytes)
    commit = client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"manifest_id": "lincoln-wheat-1909-1958"},
        headers=auth_headers,
    )
    assert commit.status_code == 200
    set_id = commit.json()["set_id"]

    needs = client.get(f"/api/v1/sets/{set_id}/needs", headers=auth_headers)
    assert needs.status_code == 200
    nbody = needs.json()
    assert nbody["set_key"] == "lincoln-wheat-1909-1958"
    assert nbody["filled"] == 2
    assert 0.0 < nbody["completion_pct"] < 100.0
    assert nbody["key_dates_missing"] >= 1

    pdf = client.get(f"/api/v1/sets/{set_id}/wantlist.pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
    assert "wantlist-lincoln-wheat" in pdf.headers["content-disposition"]


def test_wantlist_complete_set(client: TestClient, auth_headers, make_coin) -> None:
    # A tiny fully-filled set still renders a valid "Set complete" PDF.
    manifest = {
        "id": "tiny-complete",
        "name": "Tiny Complete Set",
        "composition_ref": "x",
        "slots": [{"year": 1921, "mint": "P"}],
    }
    load = client.post(
        "/api/v1/sets/load", json={"manifest": manifest}, headers=auth_headers
    )
    set_id = load.json()["set_id"]
    acc = make_coin({"year": 1921, "mintmark": "P"})
    client.post(
        f"/api/v1/sets/{set_id}/assign",
        json={"slot": {"year": 1921, "mint": "P"}, "accession": acc},
        headers=auth_headers,
    )
    needs = client.get(f"/api/v1/sets/{set_id}/needs", headers=auth_headers).json()
    assert needs["completion_pct"] == 100.0
    assert needs["missing"] == []

    pdf = client.get(f"/api/v1/sets/{set_id}/wantlist.pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_upload_after_commit_409(
    client: TestClient, auth_headers, png_bytes
) -> None:
    imp = _seed_committable(client, auth_headers, png_bytes)
    client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"manifest_id": "lincoln-wheat-1909-1958"},
        headers=auth_headers,
    )
    r = client.post(
        f"/api/v1/albums/imports/{imp}/pages",
        files=[("pages", ("x.png", png_bytes + b"z", "image/png"))],
        headers=auth_headers,
    )
    assert r.status_code == 409


def test_delete_discards(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    _upload_page(client, auth_headers, imp, png_bytes)
    r = client.delete(f"/api/v1/albums/imports/{imp}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "discarded"
    detail = client.get(f"/api/v1/albums/imports/{imp}", headers=auth_headers).json()
    assert detail["status"] == "discarded"


def test_commit_both_targets_422(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _seed_committable(client, auth_headers, png_bytes)
    r = client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"manifest_id": "lincoln-wheat-1909-1958", "custom_name": "X"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_commit_custom_name(client: TestClient, auth_headers, png_bytes) -> None:
    imp = _create_import(client, auth_headers)
    page_id = _upload_page(client, auth_headers, imp, png_bytes)
    client.post(
        f"/api/v1/albums/imports/{imp}/pages/{page_id}/analysis",
        json={
            "page_title": None,
            "page_type": "page",
            "slots": [
                {"slot_index": 0, "label_text": "1970 P", "fill_state": "filled"},
                {"slot_index": 1, "label_text": "1971 D", "fill_state": "empty"},
            ],
        },
        headers=auth_headers,
    )
    r = client.post(
        f"/api/v1/albums/imports/{imp}/commit",
        json={"custom_name": "Bicentennial Junk"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["set_key"] == "custom-bicentennial-junk"
    assert r.json()["total_slots"] == 2
