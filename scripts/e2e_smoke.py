#!/usr/bin/env python3
"""End-to-end smoke test against a scratch daemon, temp DB, and token."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

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

            melt = client.get("/api/v1/melt/status", headers=headers)
            assert melt.status_code == 200, f"melt/status: {melt.status_code} {melt.text}"
            melt_body = melt.json()
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

        print("PASS: e2e smoke ok")
        return 0
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
