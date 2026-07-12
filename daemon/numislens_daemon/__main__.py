"""Entry point for the numislens-daemon console script."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from .app import create_app

# Host defaults to 127.0.0.1; never port-forward the daemon raw — front it with
# `tailscale serve` instead.


def _resolve_db_path(args_db: str | None) -> Path:
    try:
        from numislens_core.cli import resolve_db_path

        return resolve_db_path(args_db)
    except ImportError:
        if args_db is not None:
            path = Path(args_db)
        elif os.environ.get("NUMISLENS_DB"):
            path = Path(os.environ["NUMISLENS_DB"])
        else:
            path = Path.home() / ".local" / "share" / "numislens" / "numislens.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def main() -> None:
    parser = argparse.ArgumentParser(description="NumisLens FastAPI daemon")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite database path (default: NUMISLENS_DB or ~/.local/share/numislens/numislens.db)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", default=8471, type=int, help="Bind port")
    parser.add_argument(
        "--images-dir",
        default=None,
        help="Directory for coin images (default: ~/.local/share/numislens/images)",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db)
    images_dir = Path(args.images_dir) if args.images_dir else None

    try:
        app = create_app(db_path=db_path, images_dir=images_dir)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
