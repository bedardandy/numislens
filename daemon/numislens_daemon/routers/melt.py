"""Melt and portfolio value endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from numislens_core import Ledger
from numislens_core import melt

from ..deps import get_ledger
from ..serializers import dollars

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


@router.post("/melt/update", tags=["melt"])
def update_melt(ldb: LedgerDep) -> dict:
    recorded: list[str] = []
    errors: dict[str, str] = {}
    for metal in sorted(melt.METALS):
        try:
            melt.record_spot(ldb.conn, metal)
            recorded.append(metal)
        except melt.SpotError as exc:
            errors[metal] = str(exc)

    summary = melt.update_melt_values(ldb.conn)
    newly_stale = [s for s in summary["stale_marked"] if s.get("newly")]
    # Optional keyless push (NUMISLENS_NTFY_URL); no-op when unset, and a
    # notifier failure is logged-not-fatal (never blocks this response).
    notified = melt.push_notification(ldb.conn, summary)
    return {
        "recorded": recorded,
        "errors": errors,
        "updated": len(summary["updated"]),
        "hybrid_floors": len(summary["hybrid_floors"]),
        "skipped_no_spot": len(summary["skipped_no_spot"]),
        "stale_marked": len(newly_stale),
        "notified": notified is not None,
    }


@router.get("/melt/status", tags=["melt"])
def melt_status(ldb: LedgerDep) -> dict:
    spots: dict[str, dict | None] = {}
    for metal in sorted(melt.METALS):
        latest = melt.latest_spot(ldb.conn, metal, "gold-api")
        spots[metal] = (
            {
                "price_usd_cents": latest["price_usd_cents"],
                "price_display": dollars(latest["price_usd_cents"]),
                "source": latest["source"],
                "fetched_at": latest["fetched_at"],
            }
            if latest is not None
            else None
        )

    portfolio = melt.portfolio_melt(ldb.conn)
    delta = melt.melt_delta(ldb.conn)
    return {
        "spots": spots,
        "portfolio": {
            "total_cents": portfolio["total_cents"],
            "total_display": dollars(portfolio["total_cents"]),
            "by_metal": {
                m: {"cents": c, "display": dollars(c)}
                for m, c in portfolio["by_metal"].items()
            },
        },
        "delta": delta,
    }


@router.get("/portfolio/value", tags=["melt"])
def portfolio_value(ldb: LedgerDep) -> dict:
    pv = melt.portfolio_value(ldb.conn)
    return {
        "melt": {
            "total_cents": pv["melt"]["total_cents"],
            "total_display": dollars(pv["melt"]["total_cents"]),
            "by_metal": {
                m: {"cents": c, "display": dollars(c)}
                for m, c in pv["melt"]["by_metal"].items()
            },
        },
        "value_est_by_basis": {
            b: {
                "count": v["count"],
                "value_cents": v["value_cents"],
                "value_display": dollars(v["value_cents"]),
            }
            for b, v in pv["value_est_by_basis"].items()
        },
        "value_est_total_cents": pv["value_est_total_cents"],
        "value_est_total_display": dollars(pv["value_est_total_cents"]),
    }
