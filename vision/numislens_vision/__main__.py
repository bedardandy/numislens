"""numislens-vision CLI.

- ``identify <accession>``  : run the pipeline and print the gated result (NO writes).
- ``process <accession>``   : identify + fail-safe writeback for one coin.
- ``process --pending``     : same, for every unidentified coin with images.
- ``status``                : collection-wide vision counts.
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


def _cmd_process(args: argparse.Namespace) -> int:
    from .worker import process

    cfg = load_config()
    process(cfg, accession=args.accession, pending=args.pending)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from .worker import format_status, status

    cfg = load_config()
    print(format_status(status(cfg)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="numislens-vision")
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser(
        "identify", help="run the pipeline for one coin and print the result (no writes)"
    )
    p_id.add_argument("accession", help="coin accession, e.g. NL-000123")
    p_id.set_defaults(func=_cmd_identify)

    p_pr = sub.add_parser(
        "process", help="identify + fail-safe writeback (one coin or --pending)"
    )
    g = p_pr.add_mutually_exclusive_group(required=True)
    g.add_argument("accession", nargs="?", help="coin accession, e.g. NL-000123")
    g.add_argument(
        "--pending",
        action="store_true",
        help="process every unidentified coin that has images and no vision appraisal",
    )
    p_pr.set_defaults(func=_cmd_process)

    p_st = sub.add_parser("status", help="collection-wide vision status counts")
    p_st.set_defaults(func=_cmd_status)

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
