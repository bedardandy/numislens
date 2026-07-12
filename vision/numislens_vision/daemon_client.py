"""Synchronous REST client for the NumisLens daemon.

The vision package NEVER imports numislens_core and NEVER touches the SQLite
file directly — it reaches the ledger only through the daemon's bearer-token
REST API, exactly like surfaces/mcp. This client covers the reads the pipeline
needs (coin, images, sets/key-dates) and the writes the worker needs
(identification fill-null PATCH, appraisal, digest-staleness).
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import VisionConfig


class DaemonError(Exception):
    pass


class DaemonClient:
    def __init__(self, config: VisionConfig) -> None:
        self._base = config.daemon_url
        self._headers = {"Authorization": f"Bearer {config.token}"}
        self._timeout = 30.0

    def _request(
        self, method: str, path: str, *, params: Any = None, json: Any = None
    ) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self._base, headers=self._headers, timeout=self._timeout
            ) as client:
                resp = client.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise DaemonError(
                f"cannot reach the NumisLens daemon at {self._base} — is it running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise DaemonError("request to the NumisLens daemon timed out") from exc
        if resp.status_code == 401:
            raise DaemonError(
                "unauthorized (401): NUMISLENS_TOKEN does not match the daemon token"
            )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = resp.text
            raise DaemonError(f"API error {resp.status_code}: {detail}")
        return resp

    def _json(self, method: str, path: str, **kw: Any) -> Any:
        return self._request(method, path, **kw).json()

    # ---- reads -------------------------------------------------------------

    def get_coin(self, accession: str) -> dict:
        return self._json("GET", f"/api/v1/coins/{accession}")

    def list_coins(self, **filters: Any) -> list[dict]:
        params = {k: v for k, v in filters.items() if v is not None}
        return self._json("GET", "/api/v1/coins", params=params or None)

    def get_image_bytes(self, accession: str, content_hash: str) -> bytes:
        resp = self._request(
            "GET", f"/api/v1/coins/{accession}/images/{content_hash}"
        )
        return resp.content

    def list_sets(self) -> list[dict]:
        return self._json("GET", "/api/v1/sets")

    def set_board(self, set_id: str | int) -> dict:
        return self._json("GET", f"/api/v1/sets/{set_id}/board")

    def key_date_years(self) -> set[int]:
        """Years that carry at least one key_date slot across all loaded sets.

        Conservative key-date signal for the agreement gate: if a read year
        matches any of these, the gate demands unanimity (a key date is exactly
        the ~100x-value case the whole pipeline exists to get right). Empty when
        no sets are loaded — then no extra strictness applies.
        """
        years: set[int] = set()
        for s in self.list_sets():
            key = s.get("set_key") or s.get("id")
            if key is None:
                continue
            try:
                board = self.set_board(key)
            except DaemonError:
                continue
            for slot in board.get("slots", []):
                if slot.get("key_date"):
                    years.add(int(slot["year"]))
        return years

    def known_series(self) -> list[str]:
        """Canonical series names the ledger knows (loaded sets + coins)."""
        names: set[str] = set()
        for s in self.list_sets():
            series = s.get("series")
            if series:
                names.add(series)
        for coin in self.list_coins():
            series = coin.get("series")
            if series:
                names.add(series)
        return sorted(names)

    # ---- writes ------------------------------------------------------------

    def patch_identification(self, accession: str, fields: dict[str, Any]) -> dict:
        """Fill-null-only identification writeback (see daemon PATCH /coins)."""
        return self._json(
            "PATCH", f"/api/v1/coins/{accession}", json=fields
        )

    def record_appraisal(self, accession: str, body: dict[str, Any]) -> dict:
        return self._json(
            "POST", f"/api/v1/coins/{accession}/appraise", json=body
        )

    def mark_stale_digest(
        self, accession: str, reason: str, source_note: str | None = None
    ) -> dict:
        item: dict[str, Any] = {"accessions": [accession], "reason": reason}
        if source_note:
            item["source_note"] = source_note
        return self._json(
            "POST", "/api/v1/watch/digest", json={"items": [item]}
        )
