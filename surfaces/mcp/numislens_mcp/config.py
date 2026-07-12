from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_URL = "http://127.0.0.1:8471"


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str


def load_config() -> Config:
    base_url = os.environ.get("NUMISLENS_URL", DEFAULT_URL).rstrip("/")
    token = os.environ.get("NUMISLENS_TOKEN", "")
    if not token:
        raise RuntimeError(
            'NUMISLENS_TOKEN is not set. Export the daemon bearer token, e.g. '
            'export NUMISLENS_TOKEN=... (generate one with: '
            'python3 -c "import secrets;print(secrets.token_urlsafe(32))").'
        )
    return Config(base_url=base_url, token=token)
