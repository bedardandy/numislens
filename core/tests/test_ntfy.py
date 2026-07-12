"""Tests for the optional keyless ntfy push (Phase 6)."""

import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from numislens_core import melt


class _CaptureHandler(BaseHTTPRequestHandler):
    posts: list[bytes] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        _CaptureHandler.posts.append(self.rfile.read(length))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def stub_ntfy():
    _CaptureHandler.posts = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/numislens-test", _CaptureHandler.posts
    finally:
        server.shutdown()
        server.server_close()


def _insert_spot(conn, metal, price_cents, *, source="gold-api", fetched_at=None):
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (metal, price_cents, source, fetched_at),
    )
    conn.commit()


def test_push_on_daily_delta_over_3pct(ledger, stub_ntfy):
    url, posts = stub_ntfy
    _insert_spot(ledger.conn, "XAG", 6000, fetched_at="2026-07-11T12:00:00+00:00")
    _insert_spot(ledger.conn, "XAG", 6300, fetched_at="2026-07-12T12:00:00+00:00")  # +5%
    summary = {"stale_marked": []}

    message = melt.push_notification(ledger.conn, summary, url=url)
    assert message is not None
    assert "XAG" in message
    assert len(posts) == 1
    assert b"XAG" in posts[0]


def test_push_on_newly_stale(ledger, stub_ntfy):
    url, posts = stub_ntfy
    summary = {
        "stale_marked": [
            {"accession": "NL-000001", "reason": "spot XAG moved +12.0%", "newly": True}
        ]
    }
    message = melt.push_notification(ledger.conn, summary, url=url)
    assert message is not None
    assert "newly stale" in message
    assert len(posts) == 1


def test_no_push_when_nothing_crosses(ledger, stub_ntfy):
    url, posts = stub_ntfy
    summary = {"stale_marked": []}
    message = melt.push_notification(ledger.conn, summary, url=url)
    assert message is None
    assert posts == []


def test_no_push_when_url_unset(ledger, monkeypatch):
    monkeypatch.delenv("NUMISLENS_NTFY_URL", raising=False)
    _insert_spot(ledger.conn, "XAG", 6000, fetched_at="2026-07-11T12:00:00+00:00")
    _insert_spot(ledger.conn, "XAG", 6300, fetched_at="2026-07-12T12:00:00+00:00")
    summary = {"stale_marked": []}
    # url=None and env unset -> no attempt, no error.
    assert melt.push_notification(ledger.conn, summary) is None


def test_url_from_env(ledger, stub_ntfy, monkeypatch):
    url, posts = stub_ntfy
    monkeypatch.setenv("NUMISLENS_NTFY_URL", url)
    summary = {"stale_marked": [{"accession": "NL-1", "reason": "r", "newly": True}]}
    message = melt.push_notification(ledger.conn, summary)
    assert message is not None
    assert len(posts) == 1


def test_notifier_failure_is_non_fatal(ledger, monkeypatch):
    # Point at a port nothing is listening on -> connection refused. Must NOT
    # raise; returns None; the ledger call that triggered it is unaffected.
    dead_url = "http://127.0.0.1:9/numislens-dead"
    summary = {"stale_marked": [{"accession": "NL-1", "reason": "r", "newly": True}]}
    assert melt.push_notification(ledger.conn, summary, url=dead_url) is None
