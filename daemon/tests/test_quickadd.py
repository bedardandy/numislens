"""Tests for the deterministic quick-add endpoint (POST /api/v1/coins/quick)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _quick(client: TestClient, headers: dict[str, str], text: str):
    return client.post("/api/v1/coins/quick", json={"text": text}, headers=headers)


def _make_location(client, headers, kind, label, parent_id=None):
    body = {"kind": kind, "label": label}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = client.post("/api/v1/locations", json=body, headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


def test_steel_cent_canonical_phrase(client, auth_headers):
    # "1943 steel cent, box 3 slot 12, paid $4"
    box = _make_location(client, auth_headers, "box", "3")
    _make_location(client, auth_headers, "slot", "12", parent_id=box)
    resp = _quick(client, auth_headers, "1943 steel cent, box 3 slot 12, paid $4")
    assert resp.status_code == 200
    body = resp.json()
    p = body["parsed"]
    assert p["year"] == 1943
    assert p["series"] == "Lincoln Wheat Cent"
    assert p["denomination"] == "cent"
    assert p["cost_basis_cents"] == 400  # cents exactness
    assert "composition_id" in p  # steel cent is a certain composition
    # base-metal composition -> no value_basis fabricated
    assert "value_basis" not in p
    assert p["location_id"] is not None
    assert body["unresolved"] == []
    assert body["created"].startswith("NL-")
    assert body["coin"]["cost_basis_display"] == "$4.00"


def test_morgan_dollar_with_mint_and_tray(client, auth_headers):
    # "add 1885 Morgan dollar CC to tray 2" — mintmark via series adjacency
    _make_location(client, auth_headers, "tray", "2")
    resp = _quick(client, auth_headers, "add 1885 Morgan dollar CC to tray 2")
    assert resp.status_code == 200
    p = resp.json()["parsed"]
    assert p["year"] == 1885
    assert p["series"] == "Morgan Dollar"
    assert p["mintmark"] == "CC"
    assert p["denomination"] == "dollar"
    # 1885 Morgan is a certain 90% silver dollar -> hybrid melt-floor basis
    assert "composition_id" in p
    assert p["value_basis"] == "hybrid"
    assert p["location_id"] is not None
    assert resp.json()["unresolved"] == []


def test_hyphenated_mintmark_adjacency(client, auth_headers):
    resp = _quick(client, auth_headers, "1885-CC Morgan dollar")
    assert resp.status_code == 200
    p = resp.json()["parsed"]
    assert p["year"] == 1885
    assert p["mintmark"] == "CC"


def test_space_separated_mint_after_year(client, auth_headers):
    resp = _quick(client, auth_headers, "1885 CC Morgan dollar")
    assert resp.status_code == 200
    assert resp.json()["parsed"]["mintmark"] == "CC"


def test_floating_mint_token_is_not_a_mintmark(client, auth_headers):
    # "CC" with no year/series adjacency must NOT become a mintmark — and it
    # must be reported back as unrecognized text, never silently dropped.
    resp = _quick(client, auth_headers, "CC 1900 washington quarter")
    assert resp.status_code == 200
    body = resp.json()
    assert "mintmark" not in body["parsed"]
    assert 'unrecognized: "cc"' in body["unresolved"]


def test_garbage_input_refuses_422(client, auth_headers):
    resp = _quick(client, auth_headers, "asdf qwerty zzz")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "parsed" in detail and "unresolved" in detail
    # Nothing was created.
    assert client.get("/api/v1/coins", headers=auth_headers).json() == []


def test_unresolved_location_not_autocreated(client, auth_headers):
    # box 9 does not exist; it must be listed unresolved, not created.
    resp = _quick(client, auth_headers, "1964 Kennedy half, box 9")
    assert resp.status_code == 200
    body = resp.json()
    assert "location_id" not in body["parsed"]
    assert "box 9" in body["unresolved"]
    tree = client.get("/api/v1/locations/tree", headers=auth_headers).json()
    assert tree["tree"] == []  # no location was auto-created


def test_no_composition_guess_for_generic_denomination(client, auth_headers):
    # "1964 half dollar": year + denomination only; no certain composition rule.
    resp = _quick(client, auth_headers, "1964 half dollar")
    assert resp.status_code == 200
    p = resp.json()["parsed"]
    assert p["year"] == 1964
    assert p["denomination"] == "half dollar"
    assert "series" not in p  # generic word never fabricates a series
    assert "composition_id" not in p
    assert "value_basis" not in p


def test_uncertain_composition_listed_unresolved(client, auth_headers):
    # Morgan dollar without a qualifying year -> composition uncertain.
    resp = _quick(client, auth_headers, "Morgan dollar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["series"] == "Morgan Dollar"
    assert "composition_id" not in body["parsed"]
    assert "composition" in body["unresolved"]


def test_modern_morgan_out_of_range_no_silver(client, auth_headers):
    # 2021 Morgan commemoratives are .999, not 90% silver -> not certain.
    resp = _quick(client, auth_headers, "2021 Morgan dollar")
    assert resp.status_code == 200
    body = resp.json()
    assert "composition_id" not in body["parsed"]
    assert "composition" in body["unresolved"]


def test_cents_exactness_decimal_and_commas(client, auth_headers):
    resp = _quick(client, auth_headers, "1921 Peace dollar, paid $1,234.56")
    assert resp.status_code == 200
    p = resp.json()["parsed"]
    assert p["cost_basis_cents"] == 123456
    # 1921 Peace is in the certain 90% silver range.
    assert p["value_basis"] == "hybrid"


def test_year_only_creates_minimal_coin(client, auth_headers):
    resp = _quick(client, auth_headers, "just a 1955 something")
    assert resp.status_code == 200
    p = resp.json()["parsed"]
    assert p["year"] == 1955
    assert "series" not in p
    assert resp.json()["created"].startswith("NL-")


def test_ambiguous_location_unresolved(client, auth_headers):
    # Two boxes labelled "3" -> ambiguous -> unresolved, not silently picked.
    _make_location(client, auth_headers, "box", "3")
    _make_location(client, auth_headers, "box", "3")
    resp = _quick(client, auth_headers, "1943 steel cent, box 3")
    assert resp.status_code == 200
    body = resp.json()
    assert "location_id" not in body["parsed"]
    assert "box 3" in body["unresolved"]


def test_steel_rule_is_year_gated(client, auth_headers):
    # No 1957 steel cent exists: the steel rule must NOT fire on an impossible
    # year — composition stays null and is listed unresolved (user misspoke).
    resp = _quick(client, auth_headers, "1957 steel cent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["year"] == 1957
    assert body["parsed"]["series"] == "Lincoln Wheat Cent"
    assert "composition_id" not in body["parsed"]
    assert "composition" in body["unresolved"]

    # Year absent -> the word "steel" alone still names the metal (certain).
    resp2 = _quick(client, auth_headers, "steel cent")
    assert resp2.status_code == 200
    assert "composition_id" in resp2.json()["parsed"]
    assert "composition" not in resp2.json()["unresolved"]


def test_unconsumed_text_reported_unrecognized(client, auth_headers):
    # "shoebox" is not a known location kind: the phrase must surface as an
    # unrecognized entry, not vanish silently.
    resp = _quick(client, auth_headers, "1885 Morgan dollar, shoebox 9")
    assert resp.status_code == 200
    body = resp.json()
    assert "location_id" not in body["parsed"]
    assert 'unrecognized: "shoebox 9"' in body["unresolved"]

    # Unknown series word ("Buffalo") is echoed back too.
    resp2 = _quick(client, auth_headers, "CC 1936 Buffalo nickel")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["parsed"]["year"] == 1936
    assert "mintmark" not in body2["parsed"]
    assert 'unrecognized: "cc"' in body2["unresolved"]
    assert 'unrecognized: "buffalo"' in body2["unresolved"]


def test_second_year_candidate_reported_unrecognized(client, auth_headers):
    # Multiple 4-digit years: the first is the year; the rest are surfaced.
    resp = _quick(client, auth_headers, "1943 cent bought 1999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["year"] == 1943
    assert 'unrecognized: "1999"' in body["unresolved"]


def test_unknown_field_rejected_422(client, auth_headers):
    # Strict schema: unknown keys must 422, not be silently dropped.
    resp = client.post(
        "/api/v1/coins/quick",
        json={"text": "1943 steel cent", "grade": "MS65"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
