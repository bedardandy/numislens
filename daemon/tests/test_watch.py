"""Tests for the value-watch daemon endpoints (Phase 6)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def _seed_prior_spot(db_path, metal, price_cents):
    """Insert a prior-day PRIMARY spot row so a next update has something to diff."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at) "
            "VALUES (?, ?, 'gold-api', ?)",
            (metal, price_cents, yesterday),
        )
        conn.commit()
    finally:
        conn.close()


# --- watch/status ---------------------------------------------------------


def test_watch_status_empty(client, auth_headers):
    resp = client.get("/api/v1/watch/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale_count"] == 0
    assert body["stale"] == []
    assert body["watchlist"] == []
    assert "delta" in body


def test_watch_status_watchlist_and_n(client, auth_headers, make_coin):
    make_coin({"value_est_cents": 1000, "value_basis": "numismatic"})
    make_coin({"value_est_cents": 9000, "value_basis": "numismatic"})
    make_coin({"value_est_cents": 5000, "value_basis": "numismatic"})

    resp = client.get("/api/v1/watch/status?n=2", headers=auth_headers)
    assert resp.status_code == 200
    watch = resp.json()["watchlist"]
    assert [c["value_est_cents"] for c in watch] == [9000, 5000]


# --- watch/digest ---------------------------------------------------------


def test_digest_marks_series_and_counts(client, auth_headers, make_coin):
    make_coin({"series": "Morgan Dollar"})
    make_coin({"series": "Morgan Dollar"})
    make_coin({"series": "Peace Dollar"})

    resp = client.post(
        "/api/v1/watch/digest",
        json={"items": [{"series": "Morgan Dollar", "reason": "silver rally"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"][0]["matched"] == 2
    assert body["total_marked"] == 2

    status = client.get("/api/v1/watch/status", headers=auth_headers).json()
    assert status["stale_count"] == 2


def test_digest_source_note_folded_into_reason(client, auth_headers, make_coin):
    make_coin({"series": "Morgan Dollar"})
    resp = client.post(
        "/api/v1/watch/digest",
        json={
            "items": [
                {
                    "series": "Morgan Dollar",
                    "reason": "record price",
                    "source_note": "Heritage 2026-07 sale",
                }
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    status = client.get("/api/v1/watch/status", headers=auth_headers).json()
    reason = status["stale"][0]["reason"]
    assert "record price" in reason
    assert "Heritage 2026-07 sale" in reason


def test_digest_unknown_series_422_lists_known(client, auth_headers, make_coin):
    make_coin({"series": "Morgan Dollar"})
    make_coin({"series": "Peace Dollar"})

    resp = client.post(
        "/api/v1/watch/digest",
        json={"items": [{"series": "Barber Dime", "reason": "x"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert set(detail["known_series"]) == {"Morgan Dollar", "Peace Dollar"}
    # Fail-loud & atomic: nothing was marked.
    status = client.get("/api/v1/watch/status", headers=auth_headers).json()
    assert status["stale_count"] == 0


def test_digest_accessions_target(client, auth_headers, make_coin):
    acc = make_coin({"series": "Morgan Dollar"})
    resp = client.post(
        "/api/v1/watch/digest",
        json={"items": [{"accessions": [acc], "reason": "auction"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["matched"] == 1


def test_digest_item_needs_exactly_one_target(client, auth_headers, make_coin):
    make_coin({"series": "Morgan Dollar"})
    resp = client.post(
        "/api/v1/watch/digest",
        json={"items": [{"reason": "no target"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "exactly one" in resp.json()["detail"]["message"]


def test_digest_rejects_unknown_field(client, auth_headers):
    resp = client.post(
        "/api/v1/watch/digest",
        json={"items": [{"series": "X", "reason": "y", "bogus": 1}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# --- appraise clears staleness -------------------------------------------


def test_appraise_clears_staleness(client, auth_headers, make_coin):
    acc = make_coin({"series": "Morgan Dollar", "value_basis": "numismatic"})
    client.post(
        "/api/v1/watch/digest",
        json={"items": [{"accessions": [acc], "reason": "silver moved"}]},
        headers=auth_headers,
    )
    assert client.get("/api/v1/watch/status", headers=auth_headers).json()["stale_count"] == 1

    appr = client.post(
        f"/api/v1/coins/{acc}/appraise",
        json={"appraised_by": "human", "value_cents": 5000, "value_basis": "numismatic"},
        headers=auth_headers,
    )
    assert appr.status_code == 200
    assert client.get("/api/v1/watch/status", headers=auth_headers).json()["stale_count"] == 0


# --- ntfy on melt/update --------------------------------------------------


class _CaptureHandler(BaseHTTPRequestHandler):
    posts: list[bytes] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        _CaptureHandler.posts.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_ntfy():
    _CaptureHandler.posts = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/nl", _CaptureHandler.posts
    finally:
        server.shutdown()
        server.server_close()


def test_melt_update_pushes_ntfy_on_new_stale(
    client, auth_headers, make_coin, db_path, patch_spot, stub_ntfy, monkeypatch
):
    url, posts = stub_ntfy
    # A hybrid silver coin (composition 4 = 90% silver dollar, XAG).
    make_coin({"value_basis": "hybrid"})
    # Prior primary XAG row well below the patched 6001 so the new row is >10% up.
    _seed_prior_spot(db_path, "XAG", 5300)
    patch_spot(gold_cents=6001, yahoo_cents=6010)
    monkeypatch.setenv("NUMISLENS_NTFY_URL", url)

    resp = client.post("/api/v1/melt/update", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stale_marked"] >= 1
    assert body["notified"] is True
    assert len(posts) == 1
