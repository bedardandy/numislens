"""numislens-vision CLI.

Checkpoint A ships the read-only ``identify`` subcommand (runs the pipeline and
prints the gated result, no writes). Checkpoint B adds ``process`` (writeback)
and ``status``.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config


def _cmd_identify(args: argparse.Namespace) -> int:
    from .pipeline import identify

    cfg = load_config()
    result = identify(cfg, args.accession)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="numislens-vision")
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser(
        "identify", help="run the pipeline for one coin and print the result (no writes)"
    )
    p_id.add_argument("accession", help="coin accession, e.g. NL-000123")
    p_id.set_defaults(func=_cmd_identify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # fail loud, print the error, non-zero exit
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
