#!/usr/bin/env python3
"""End-to-end smoke test against a scratch daemon, temp DB, and token."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from numislens_core import melt
from numislens_daemon.app import create_app

SPOT_PRICES = {
    "XAG": 6001,
    "XAU": 412140,
    "XPT": 95000,
}
SPOT_SOURCES = ("gold-api", "yahoo")


def main() -> int:
    try:
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tempdir = Path(tmp)
            db_path = tempdir / "nl.db"
            images = tempdir / "img"
            images.mkdir()

            app = create_app(db_path=db_path, images_dir=images, token="smoke-token")
            client = TestClient(app)
            headers = {"Authorization": "Bearer smoke-token"}

            manifest_path = str(
                (root / "core" / "sets" / "washington-quarters-1932-1964.json").resolve()
            )
            load = client.post(
                "/api/v1/sets/load",
                json={"manifest_path": manifest_path},
                headers=headers,
            )
            assert load.status_code == 200, f"sets/load: {load.status_code} {load.text}"
            set_id = load.json()["set_id"]
            print(f"loaded set_id={set_id}")

            status0 = client.get(f"/api/v1/sets/{set_id}/status", headers=headers).json()
            filled0 = status0["filled"]
            gaps0 = status0["gaps"]
            print(f"status0: filled={filled0} gaps={gaps0} total={status0['total']}")

            coins = [
                {
                    "series": "Washington Quarter",
                    "year": 1932,
                    "mintmark": "P",
                    "grade_bucket": "XF",
                    "value_basis": "melt",
                },
                {
                    "series": "Washington Quarter",
                    "year": 1932,
                    "mintmark": "D",
                    "grade_bucket": "VF",
                    "value_basis": "melt",
                },
            ]
            accessions: list[str] = []
            for coin in coins:
                created = client.post("/api/v1/coins", json=coin, headers=headers)
                assert created.status_code == 201, (
                    f"coins create: {created.status_code} {created.text}"
                )
                accession = created.json()["accession_no"]
                accessions.append(accession)
                print(f"created coin {coin['mintmark']}: accession_no={accession}")

            slots = [
                {"year": 1932, "mint": "P"},
                {"year": 1932, "mint": "D"},
            ]
            for slot, accession in zip(slots, accessions):
                assigned = client.post(
                    f"/api/v1/sets/{set_id}/assign",
                    json={"slot": slot, "accession": accession},
                    headers=headers,
                )
                assert assigned.status_code == 200, (
                    f"assign {slot}: {assigned.status_code} {assigned.text}"
                )
                print(f"assigned {slot['mint']} -> {accession}")

            status1 = client.get(f"/api/v1/sets/{set_id}/status", headers=headers).json()
            assert status1["filled"] == filled0 + 2, (
                f"filled expected {filled0 + 2}, got {status1['filled']}"
            )
            assert status1["gaps"] == gaps0 - 2, (
                f"gaps expected {gaps0 - 2}, got {status1['gaps']}"
            )
            print(f"status1: filled={status1['filled']} gaps={status1['gaps']}")

            board_resp = client.get(f"/api/v1/sets/{set_id}/board", headers=headers)
            assert board_resp.status_code == 200
            board = board_resp.json()
            assert board["total"] == status1["filled"] + status1["gaps"], (
                f"board total {board['total']} != filled+gaps "
                f"{status1['filled'] + status1['gaps']}"
            )
            assert len(board["slots"]) == board["total"]
            assert any(s["accession"] for s in board["slots"])
            print(f"board: total={board['total']} slots={len(board['slots'])}")

            fetched_at = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(str(db_path))
            try:
                for metal, price_cents in SPOT_PRICES.items():
                    for source in SPOT_SOURCES:
                        conn.execute(
                            """
                            INSERT INTO spot_prices
                                (metal, price_usd_cents, source, fetched_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (metal, price_cents, source, fetched_at),
                        )
                conn.commit()
            finally:
                conn.close()
            print(f"seeded spot_prices at {fetched_at}")

            melt_resp = client.get("/api/v1/melt/status", headers=headers)
            assert melt_resp.status_code == 200, (
                f"melt/status: {melt_resp.status_code} {melt_resp.text}"
            )
            melt_body = melt_resp.json()
            xag = melt_body["spots"]["XAG"]
            assert xag is not None
            assert "price_display" in xag
            assert xag["source"] == "gold-api"
            assert "fetched_at" in xag
            print(f"melt XAG spot: {json.dumps(xag)}")

            portfolio = client.get("/api/v1/portfolio/value", headers=headers)
            assert portfolio.status_code == 200, (
                f"portfolio/value: {portfolio.status_code} {portfolio.text}"
            )
            portfolio_body = portfolio.json()
            assert "value_est_by_basis" in portfolio_body
            print(
                "portfolio value_est_by_basis keys: "
                f"{sorted(portfolio_body['value_est_by_basis'].keys())}"
            )

            # ---- Value-watch (Phase 6) --------------------------------------
            # A hybrid silver coin (composition 4 = 90% silver dollar, XAG) with
            # a numismatic premium. A >=10% spot move should flag it stale.
            hybrid = client.post(
                "/api/v1/coins",
                json={
                    "series": "Morgan Dollar",
                    "year": 1889,
                    "mintmark": "P",
                    "composition_id": 4,
                    "value_basis": "hybrid",
                    "value_est_cents": 8000,
                },
                headers=headers,
            )
            assert hybrid.status_code == 201, hybrid.text
            hybrid_acc = hybrid.json()["accession_no"]
            print(f"created hybrid coin {hybrid_acc} (Morgan Dollar)")

            # Prior-day XAG primary row well below the seeded 6001 -> ~13% jump.
            conn = sqlite3.connect(str(db_path))
            try:
                yesterday = (
                    datetime.now(timezone.utc) - timedelta(days=1)
                ).isoformat()
                conn.execute(
                    "INSERT INTO spot_prices (metal, price_usd_cents, source, fetched_at)"
                    " VALUES ('XAG', 5300, 'gold-api', ?)",
                    (yesterday,),
                )
                conn.commit()
            finally:
                conn.close()

            # Deterministic melt recompute (no network): trips the >=10% trigger.
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                summary = melt.update_melt_values(conn)
            finally:
                conn.close()
            newly = [s for s in summary["stale_marked"] if s.get("newly")]
            assert newly, f"expected a >=10% spot trigger, got {summary['stale_marked']}"
            print(f"spot-move trigger marked stale: {[s['accession'] for s in newly]}")

            watch = client.get("/api/v1/watch/status", headers=headers).json()
            assert watch["stale_count"] >= 1, watch
            assert any(s["accession"] == hybrid_acc for s in watch["stale"]), watch
            print(
                f"watch/status: stale_count={watch['stale_count']} "
                f"watchlist={len(watch['watchlist'])}"
            )

            # Digest with a series we hold -> marks + per-item count.
            dig = client.post(
                "/api/v1/watch/digest",
                json={
                    "items": [
                        {
                            "series": "Morgan Dollar",
                            "reason": "strong auction results",
                            "source_note": "smoke-test citation",
                        }
                    ]
                },
                headers=headers,
            )
            assert dig.status_code == 200, dig.text
            assert dig.json()["items"][0]["matched"] >= 1, dig.text
            print(f"digest (known series) matched={dig.json()['items'][0]['matched']}")

            # Digest with an unknown series -> 422 listing what exists.
            bad = client.post(
                "/api/v1/watch/digest",
                json={"items": [{"series": "Barber Dime", "reason": "x"}]},
                headers=headers,
            )
            assert bad.status_code == 422, bad.text
            known = bad.json()["detail"]["known_series"]
            assert "Morgan Dollar" in known, known
            print(f"digest (unknown series) -> 422, known_series={known}")

            # Appraise the stale coin -> staleness cleared.
            appr = client.post(
                f"/api/v1/coins/{hybrid_acc}/appraise",
                json={
                    "appraised_by": "smoke",
                    "value_cents": 8500,
                    "value_basis": "numismatic",
                    "rationale": "post-digest re-check",
                },
                headers=headers,
            )
            assert appr.status_code == 200, appr.text
            cleared = client.get(
                f"/api/v1/coins/{hybrid_acc}", headers=headers
            ).json()
            assert cleared["stale_since"] is None, cleared
            print(f"appraised {hybrid_acc}: staleness cleared (stale_since=None)")

        print("PASS: e2e smoke ok")
        return 0
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
