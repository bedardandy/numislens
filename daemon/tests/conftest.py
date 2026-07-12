"""Pytest fixtures for the NumisLens daemon."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from numislens_daemon.app import create_app


@pytest.fixture
def token() -> str:
    return "test-token-123"


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def images_dir(tmp_path) -> Path:
    return tmp_path / "images"


@pytest.fixture
def client(db_path, images_dir, token: str) -> TestClient:
    app = create_app(db_path=db_path, images_dir=images_dir, token=token)
    return TestClient(app)


@pytest.fixture
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def png_bytes() -> bytes:
    def _png() -> bytes:
        def chunk(typ: bytes, data: bytes) -> bytes:
            c = typ + data
            return (
                struct.pack(">I", len(data))
                + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            )

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        idat = zlib.compress(b"\x00\xff\x00\x00")
        return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

    return _png()


@pytest.fixture
def make_coin(
    client: TestClient, auth_headers: dict[str, str]
) -> Callable[..., str]:
    default = {
        "series": "Peace Dollar",
        "year": 1921,
        "mintmark": "P",
        "denomination": "dollar",
        "composition_id": 4,
        "value_basis": "melt",
        "cost_basis_cents": 5000,
    }

    def _make_coin(coin_data: dict | None = None) -> str:
        payload = {**default, **(coin_data or {})}
        response = client.post("/api/v1/coins", json=payload, headers=auth_headers)
        assert response.status_code == 201
        return response.json()["accession_no"]

    return _make_coin


@pytest.fixture
def patch_spot(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def _patch_spot(gold_cents: int = 6001, yahoo_cents: int = 6010) -> None:
        monkeypatch.setattr(
            "numislens_core.melt._fetch_gold_api",
            lambda metal: (gold_cents, datetime.now(timezone.utc).isoformat()),
        )
        monkeypatch.setattr(
            "numislens_core.melt._fetch_yahoo",
            lambda metal: yahoo_cents,
        )

    return _patch_spot
