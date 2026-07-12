"""Bearer token authentication for the NumisLens daemon."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[len("Bearer ") :]
    expected = request.app.state.numislens_token
    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=401,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return None
