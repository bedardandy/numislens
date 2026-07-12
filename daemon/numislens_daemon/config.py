"""Daemon configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def resolve_token() -> str | None:
    env_token = os.environ.get("NUMISLENS_TOKEN")
    if env_token:
        stripped = env_token.strip()
        if stripped:
            return stripped

    token_path = Path.home() / ".config" / "numislens" / "token"
    if token_path.is_file():
        mode = token_path.stat().st_mode & 0o777
        if mode != 0o600:
            raise RuntimeError(
                f"token file {token_path} has insecure permissions {mode:o}; "
                "run: chmod 600 "
                f"{token_path}"
            )
        stripped = token_path.read_text(encoding="utf-8").strip()
        if stripped:
            return stripped

    return None


@dataclass(frozen=True)
class Settings:
    db_path: str | Path
    images_dir: Path = field(
        default_factory=lambda: Path.home() / ".local" / "share" / "numislens" / "images"
    )
