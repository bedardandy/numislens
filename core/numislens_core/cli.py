"""Command-line interface for the NumisLens coin ledger."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import ledger, melt


def resolve_db_path(args_db: str | None) -> Path:
    if args_db is not None:
        path = Path(args_db)
    elif os.environ.get("NUMISLENS_DB"):
        path = Path(os.environ["NUMISLENS_DB"])
    else:
        path = Path.home() / ".local" / "share" / "numislens" / "numislens.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _dollars(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.2f}"


def _dollars_to_cents(dollars: float) -> int:
    return round(dollars * 100)


def _parse_set_id(raw: str) -> int | str:
    try:
        return int(raw)
    except ValueError:
        return raw


def _cmd_error(fn):
    def wrapper(*args, **kwargs) -> int:
        try:
            return fn(*args, **kwargs)
        except (ledger.LedgerError, melt.SpotError, ValueError, FileNotFoundError) as exc:
            return _fail(str(exc))

    return wrapper


def _open_ledger(path: Path) -> ledger.Ledger:
    return ledger.Ledger(path)


@_cmd_error
def cmd_init(path: Path) -> int:
    _open_ledger(path)
    print(f"initialized {path}")
    return 0


@_cmd_error
def cmd_add(path: Path, args: argparse.Namespace) -> int:
    kwargs: dict = {}
    if args.series is not None:
        kwargs["series"] = args.series
    if args.year is not None:
        kwargs["year"] = args.year
    if args.mint is not None:
        kwargs["mintmark"] = args.mint
    if args.denomination is not None:
        kwargs["denomination"] = args.denomination
    if args.country is not None:
        kwargs["country"] = args.country
    if args.composition is not None:
        kwargs["composition_id"] = args.composition
    if args.grade is not None:
        kwargs["grade_bucket"] = args.grade
    if args.grade_source is not None:
        kwargs["grade_source"] = args.grade_source
    if args.tpg_cert is not None:
        kwargs["tpg_cert"] = args.tpg_cert
    if args.weight_g is not None:
        kwargs["weight_g"] = args.weight_g
    if args.diameter_mm is not None:
        kwargs["diameter_mm"] = args.diameter_mm
    if args.cost is not None:
        kwargs["cost_basis_cents"] = _dollars_to_cents(args.cost)
    if args.acquired_date is not None:
        kwargs["acquired_date"] = args.acquired_date
    if args.acquired_source is not None:
        kwargs["acquired_source"] = args.acquired_source
    if args.value is not None:
        kwargs["value_est_cents"] = _dollars_to_cents(args.value)
    if args.value_basis is not None:
        kwargs["value_basis"] = args.value_basis
    if args.confidence is not None:
        kwargs["appraisal_confidence"] = args.confidence
    if args.location is not None:
        kwargs["location_id"] = args.location
    if args.notes is not None:
        kwargs["notes"] = args.notes

    ldb = _open_ledger(path)
    try:
        accession = ldb.add_coin(**kwargs)
    finally:
        ldb.close()
    print(accession)
    return 0


@_cmd_error
def cmd_move(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        ldb.move_coin(args.accession, args.location_id)
    finally:
        ldb.close()
    print(f"moved {args.accession} -> location {args.location_id}")
    return 0


@_cmd_error
def cmd_show(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        coin = ldb.get_coin(args.accession)
        if coin is None:
            return _fail(f"coin not found: {args.accession}")
        if args.json:
            print(json.dumps(coin, indent=2, default=str))
            return 0
        lines = [
            f"accession: {coin['accession_no']}",
            f"series: {coin.get('series') or ''}",
            f"year: {coin.get('year') or ''}",
            f"mintmark: {coin.get('mintmark') or ''}",
            f"denomination: {coin.get('denomination') or ''}",
            f"grade: {coin.get('grade_bucket') or ''}",
            f"value: {_dollars(coin.get('value_est_cents'))}",
            f"value_basis: {coin.get('value_basis') or ''}",
        ]
        if coin.get("location_id") is not None:
            lines.append(f"location: {ldb.location_path(coin['location_id'])}")
        print("\n".join(lines))
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_find(path: Path, args: argparse.Namespace) -> int:
    filters: dict = {}
    if args.series is not None:
        filters["series"] = args.series
    if args.year is not None:
        filters["year"] = args.year
    if args.mint is not None:
        filters["mintmark"] = args.mint
    if args.denomination is not None:
        filters["denomination"] = args.denomination
    if args.grade is not None:
        filters["grade_bucket"] = args.grade
    if args.composition is not None:
        filters["composition_id"] = args.composition
    if args.location is not None:
        filters["location_id"] = args.location

    ldb = _open_ledger(path)
    try:
        results = ldb.find_coins(**filters)
        if args.json:
            print(json.dumps(results, indent=2, default=str))
            return 0
        for coin in results:
            year = coin.get("year") or ""
            mint = coin.get("mintmark") or ""
            series = coin.get("series") or ""
            value = _dollars(coin.get("value_est_cents"))
            print(f"{coin['accession_no']}  {year}  {mint}  {series}  {value}")
        print(f"{len(results)} coin(s)")
    finally:
        ldb.close()
    return 0


def _print_location_tree(
    children: dict[int | None, list[dict]], parent_id: int | None, depth: int
) -> None:
    for row in children.get(parent_id, []):
        indent = "  " * depth
        print(f"{indent}[{row['id']}] {row['kind']}: {row['label']}")
        _print_location_tree(children, row["id"], depth + 1)


@_cmd_error
def cmd_loc_add(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        location_id = ldb.create_location(args.kind, args.label, parent=args.parent)
    finally:
        ldb.close()
    print(location_id)
    return 0


@_cmd_error
def cmd_loc_tree(path: Path) -> int:
    ldb = _open_ledger(path)
    try:
        rows = ldb.conn.execute(
            "SELECT id, parent_id, kind, label FROM locations ORDER BY id"
        ).fetchall()
        children: dict[int | None, list[dict]] = {}
        for row in rows:
            parent_id = row["parent_id"]
            children.setdefault(parent_id, []).append(dict(row))
        _print_location_tree(children, None, 0)
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_set_load(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        set_id = ldb.load_set_manifest(args.path)
    finally:
        ldb.close()
    print(f"loaded set {set_id}")
    return 0


@_cmd_error
def cmd_set_gaps(path: Path, args: argparse.Namespace) -> int:
    set_id = _parse_set_id(args.set_id)
    ldb = _open_ledger(path)
    try:
        gaps = ldb.set_gaps(set_id)
        if args.json:
            print(json.dumps(gaps, indent=2, default=str))
            return 0
        for gap in gaps:
            key = " KEY" if gap.get("key_date") else ""
            print(f"{gap['year']} {gap['mint']} {gap.get('note', '')}{key}")
        print(f"{len(gaps)} gap(s)")
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_set_status(path: Path, args: argparse.Namespace) -> int:
    set_id = _parse_set_id(args.set_id)
    ldb = _open_ledger(path)
    try:
        filled, total = ldb.set_completion(set_id)
        gaps = ldb.set_gaps(set_id)
        if args.json:
            print(
                json.dumps(
                    {"filled": filled, "total": total, "gaps": len(gaps)},
                    indent=2,
                )
            )
            return 0
        print(f"{filled}/{total} filled, {len(gaps)} gap(s)")
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_appraise(path: Path, args: argparse.Namespace) -> int:
    kwargs: dict = {}
    if args.grade is not None:
        kwargs["grade_bucket"] = args.grade
    if args.value is not None:
        kwargs["value_cents"] = _dollars_to_cents(args.value)
    if args.value_basis is not None:
        kwargs["value_basis"] = args.value_basis
    if args.rationale is not None:
        kwargs["rationale"] = args.rationale
    if args.confidence is not None:
        kwargs["confidence"] = args.confidence

    ldb = _open_ledger(path)
    try:
        appraisal_id = ldb.record_appraisal(args.accession, args.by, **kwargs)
    finally:
        ldb.close()
    print(f"recorded appraisal {appraisal_id} for {args.accession}")
    return 0


def cmd_melt_update(path: Path) -> int:
    try:
        ldb = _open_ledger(path)
        failures = False
        try:
            for metal in sorted(melt.METALS):
                try:
                    melt.record_spot(ldb.conn, metal)
                    print(f"{metal}: recorded")
                except melt.SpotError as exc:
                    print(f"{metal}: ERROR {exc}", file=sys.stderr)
                    failures = True

            summary = melt.update_melt_values(ldb.conn)
            print(f"updated {len(summary['updated'])} melt-basis coin(s)")
            if summary["hybrid_floors"]:
                print(f"hybrid floors: {len(summary['hybrid_floors'])}")
            if summary["skipped_no_spot"]:
                print(f"skipped (no spot): {len(summary['skipped_no_spot'])}")
            newly_stale = [s for s in summary["stale_marked"] if s.get("newly")]
            if newly_stale:
                print(f"marked stale (spot moved >=10%): {len(newly_stale)}")
            # Optional keyless push (NUMISLENS_NTFY_URL); no-op when unset,
            # logged-not-fatal on failure.
            sent = melt.push_notification(ldb.conn, summary)
            if sent is not None:
                print(f"notified: {sent}")
        finally:
            ldb.close()
        return 1 if failures else 0
    except (ledger.LedgerError, ValueError, FileNotFoundError) as exc:
        return _fail(str(exc))


@_cmd_error
def cmd_melt_status(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        spots: dict[str, dict | None] = {}
        for metal in sorted(melt.METALS):
            row = ldb.conn.execute(
                """
                SELECT price_usd_cents, fetched_at FROM spot_prices
                WHERE metal = ? AND source = 'gold-api'
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (metal,),
            ).fetchone()
            if row is None:
                spots[metal] = None
            else:
                spots[metal] = {
                    "price_usd_cents": row["price_usd_cents"],
                    "fetched_at": row["fetched_at"],
                }

        portfolio = melt.portfolio_melt(ldb.conn)
        delta = melt.melt_delta(ldb.conn)

        if args.json:
            print(
                json.dumps(
                    {"spots": spots, "portfolio": portfolio, "delta": delta},
                    indent=2,
                    default=str,
                )
            )
            return 0

        print("Spot prices:")
        for metal in sorted(melt.METALS):
            spot = spots[metal]
            if spot is None:
                print(f"  {metal}: no data")
            else:
                price = _dollars(spot["price_usd_cents"])
                print(f"  {metal}: {price}/ozt @ {spot['fetched_at']}")

        total = _dollars(portfolio["total_cents"])
        by_metal = ", ".join(
            f"{metal} {_dollars(cents)}"
            for metal, cents in sorted(portfolio["by_metal"].items())
        )
        print(f"Portfolio melt: {total}" + (f" ({by_metal})" if by_metal else ""))

        print("Daily change:")
        for metal in sorted(delta):
            info = delta[metal]
            pct = info["pct"]
            line = f"  {metal}: {pct:+.1f}%"
            if abs(pct) > 3.0:
                line += "  <-- ALERT (>3%)"
            print(line)
    finally:
        ldb.close()
    return 0


def _coin_line(coin: dict) -> str:
    year = coin.get("year") or ""
    mint = coin.get("mintmark") or ""
    series = coin.get("series") or ""
    value = _dollars(coin.get("value_est_cents"))
    return f"{coin['accession_no']}  {year}  {mint}  {series}  {value}"


@_cmd_error
def cmd_watch_status(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        stale = ldb.list_stale()
        watch = ldb.watchlist(args.n)
        delta = melt.melt_delta(ldb.conn)
        if args.json:
            print(
                json.dumps(
                    {
                        "stale_count": len(stale),
                        "watchlist": watch,
                        "delta": delta,
                    },
                    indent=2,
                    default=str,
                )
            )
            return 0
        print(f"stale coins: {len(stale)}")
        print(f"watchlist (top {args.n} by value):")
        for coin in watch:
            print(f"  {_coin_line(coin)}")
        print("Spot deltas:")
        for metal in sorted(delta):
            print(f"  {metal}: {delta[metal]['pct']:+.1f}%")
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_watch_stale(path: Path, args: argparse.Namespace) -> int:
    ldb = _open_ledger(path)
    try:
        stale = ldb.list_stale()
        if args.json:
            print(json.dumps(stale, indent=2, default=str))
            return 0
        for coin in stale:
            print(f"{_coin_line(coin)}  <- {coin.get('stale_reason') or ''}")
        print(f"{len(stale)} stale coin(s)")
    finally:
        ldb.close()
    return 0


@_cmd_error
def cmd_watch_mark(path: Path, args: argparse.Namespace) -> int:
    targets = [t for t in (args.series, args.set_id, args.accession) if t]
    if len(targets) != 1:
        return _fail("provide exactly one of --series, --set-id, or --accession")
    ldb = _open_ledger(path)
    try:
        if args.series:
            count = ldb.mark_stale(series=args.series, reason=args.reason)
        elif args.set_id:
            count = ldb.mark_stale(set_id=_parse_set_id(args.set_id), reason=args.reason)
        else:
            count = ldb.mark_stale(accessions=args.accession, reason=args.reason)
    finally:
        ldb.close()
    print(f"marked {count} coin(s) stale")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NumisLens coin ledger")
    parser.add_argument(
        "--db",
        help="SQLite database path (overrides NUMISLENS_DB and default)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize (migrate) the database")

    add_p = subparsers.add_parser("add", help="Add a coin to the ledger")
    add_p.add_argument("--series")
    add_p.add_argument("--year", type=int)
    add_p.add_argument("--mint", help="Mint mark")
    add_p.add_argument("--denomination")
    add_p.add_argument("--country", default="US")
    add_p.add_argument("--composition", type=int, help="composition_id")
    add_p.add_argument("--grade", help="grade_bucket")
    add_p.add_argument("--grade-source")
    add_p.add_argument("--tpg-cert")
    add_p.add_argument("--weight-g", type=float)
    add_p.add_argument("--diameter-mm", type=float)
    add_p.add_argument("--cost", type=float, help="Cost in dollars")
    add_p.add_argument("--acquired-date")
    add_p.add_argument("--acquired-source")
    add_p.add_argument("--value", type=float, help="Estimated value in dollars")
    add_p.add_argument("--value-basis")
    add_p.add_argument("--confidence", type=float)
    add_p.add_argument("--location", type=int, help="location_id")
    add_p.add_argument("--notes")

    move_p = subparsers.add_parser("move", help="Move a coin to a location")
    move_p.add_argument("accession")
    move_p.add_argument("location_id", type=int)

    show_p = subparsers.add_parser("show", help="Show coin details")
    show_p.add_argument("accession")
    show_p.add_argument("--json", action="store_true")

    find_p = subparsers.add_parser("find", help="Find coins matching filters")
    find_p.add_argument("--series")
    find_p.add_argument("--year", type=int)
    find_p.add_argument("--mint")
    find_p.add_argument("--denomination")
    find_p.add_argument("--grade")
    find_p.add_argument("--composition", type=int)
    find_p.add_argument("--location", type=int)
    find_p.add_argument("--json", action="store_true")

    loc_p = subparsers.add_parser("loc", help="Location management")
    loc_sub = loc_p.add_subparsers(dest="loc_command", required=True)
    loc_add_p = loc_sub.add_parser("add", help="Create a location")
    loc_add_p.add_argument("--parent", type=int)
    loc_add_p.add_argument("kind")
    loc_add_p.add_argument("label")
    loc_sub.add_parser("tree", help="Show location tree")

    set_p = subparsers.add_parser("set", help="Set manifest management")
    set_sub = set_p.add_subparsers(dest="set_command", required=True)
    set_load_p = set_sub.add_parser("load", help="Load a set manifest")
    set_load_p.add_argument("path")
    set_gaps_p = set_sub.add_parser("gaps", help="List unfilled set slots")
    set_gaps_p.add_argument("set_id")
    set_gaps_p.add_argument("--json", action="store_true")
    set_status_p = set_sub.add_parser("status", help="Set completion status")
    set_status_p.add_argument("set_id")
    set_status_p.add_argument("--json", action="store_true")

    appraise_p = subparsers.add_parser("appraise", help="Record an appraisal")
    appraise_p.add_argument("accession")
    appraise_p.add_argument("--by", required=True)
    appraise_p.add_argument("--grade", help="grade_bucket")
    appraise_p.add_argument("--value", type=float, help="Value in dollars")
    appraise_p.add_argument("--value-basis")
    appraise_p.add_argument("--rationale")
    appraise_p.add_argument("--confidence", type=float)

    melt_p = subparsers.add_parser("melt", help="Spot price and melt values")
    melt_sub = melt_p.add_subparsers(dest="melt_command", required=True)
    melt_sub.add_parser("update", help="Fetch spot prices and update melt values")
    melt_status_p = melt_sub.add_parser("status", help="Show melt portfolio status")
    melt_status_p.add_argument("--json", action="store_true")

    watch_p = subparsers.add_parser("watch", help="Value-watch: staleness and watchlist")
    watch_sub = watch_p.add_subparsers(dest="watch_command", required=True)
    watch_status_p = watch_sub.add_parser(
        "status", help="Stale count, watchlist, and spot deltas"
    )
    watch_status_p.add_argument("--n", type=int, default=25, help="watchlist size")
    watch_status_p.add_argument("--json", action="store_true")
    watch_stale_p = watch_sub.add_parser("stale", help="List currently-stale coins")
    watch_stale_p.add_argument("--json", action="store_true")
    watch_mark_p = watch_sub.add_parser(
        "mark", help="Flag coins stale (one of --series/--set-id/--accession)"
    )
    watch_mark_p.add_argument("--series")
    watch_mark_p.add_argument("--set-id", dest="set_id")
    watch_mark_p.add_argument(
        "--accession", action="append", help="repeatable; accession to mark"
    )
    watch_mark_p.add_argument("--reason", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = resolve_db_path(args.db)

    if args.command == "init":
        return cmd_init(path)
    if args.command == "add":
        return cmd_add(path, args)
    if args.command == "move":
        return cmd_move(path, args)
    if args.command == "show":
        return cmd_show(path, args)
    if args.command == "find":
        return cmd_find(path, args)
    if args.command == "loc":
        if args.loc_command == "add":
            return cmd_loc_add(path, args)
        if args.loc_command == "tree":
            return cmd_loc_tree(path)
    if args.command == "set":
        if args.set_command == "load":
            return cmd_set_load(path, args)
        if args.set_command == "gaps":
            return cmd_set_gaps(path, args)
        if args.set_command == "status":
            return cmd_set_status(path, args)
    if args.command == "appraise":
        return cmd_appraise(path, args)
    if args.command == "melt":
        if args.melt_command == "update":
            return cmd_melt_update(path)
        if args.melt_command == "status":
            return cmd_melt_status(path, args)
    if args.command == "watch":
        if args.watch_command == "status":
            return cmd_watch_status(path, args)
        if args.watch_command == "stale":
            return cmd_watch_stale(path, args)
        if args.watch_command == "mark":
            return cmd_watch_mark(path, args)

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
