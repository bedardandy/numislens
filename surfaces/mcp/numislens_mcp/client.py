from __future__ import annotations

from typing import Any

import httpx

from .config import Config


class NumisLensError(Exception):
    pass


class NumisLensClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._headers = {"Authorization": f"Bearer {config.token}"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._config.base_url,
                headers=self._headers,
                timeout=30.0,
            ) as client:
                resp = await client.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise NumisLensError(
                "Cannot reach the NumisLens daemon at "
                f"{self._config.base_url} — is it running? Start it with: numislens-daemon"
            ) from exc
        except httpx.TimeoutException as exc:
            raise NumisLensError("Request to the NumisLens daemon timed out.") from exc

        if resp.status_code == 401:
            raise NumisLensError(
                "Unauthorized (401): check NUMISLENS_TOKEN matches the daemon bearer token."
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
                detail = body.get("detail") if isinstance(body, dict) else resp.text
            except Exception:
                detail = resp.text
            raise NumisLensError(f"API error {resp.status_code}: {detail}")

        return resp

    async def request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        return (await self.request(method, path, **kwargs)).json()
