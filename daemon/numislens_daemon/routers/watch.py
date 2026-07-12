"""Value-watch endpoints: staleness status and the digest sink."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from numislens_core import Ledger, UnknownSeries
from numislens_core import melt

from ..deps import get_ledger
from ..schemas import DigestBody
from ..serializers import serialize_coin

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


@router.get("/watch/status", tags=["watch"])
def watch_status(ldb: LedgerDep, n: int = 25) -> dict:
    """Value-watch snapshot: stale coins, the top-value watchlist, spot deltas.

    ``n`` bounds the watchlist (top coins by ``value_est_cents``). The ``stale``
    list is capped at 100 entries; ``stale_count`` is the true total.
    """
    stale = ldb.list_stale()
    stale_view = [
        {
            "accession": c["accession_no"],
            "series": c.get("series"),
            "year": c.get("year"),
            "mintmark": c.get("mintmark"),
            "value_est_cents": c.get("value_est_cents"),
            "reason": c.get("stale_reason"),
            "since": c.get("stale_since"),
        }
        for c in stale[:100]
    ]
    watchlist = [serialize_coin(c) for c in ldb.watchlist(n)]
    return {
        "stale_count": len(stale),
        "stale": stale_view,
        "watchlist": watchlist,
        "delta": melt.melt_delta(ldb.conn),
    }


@router.post("/watch/digest", tags=["watch"])
def submit_digest(body: DigestBody, ldb: LedgerDep) -> dict:
    """Deterministic sink for a weekly market digest — mark coins stale in bulk.

    Each item names EXACTLY ONE target (series, set_id, or accessions) plus a
    reason; the daemon marks the matching coins stale and reports the per-item
    matched-coin count. This never changes any value — it only flags coins for a
    later lazy re-appraisal.

    Fail-loud contract: an unknown series returns HTTP 422 with the list of
    series that DO exist (nothing is marked). An item that does not name exactly
    one target is also a 422. Do not mark stale on a hunch — cite a source_note.
    """
    # Validate shape (exactly one target per item) and pre-validate series
    # BEFORE marking anything, so the batch is all-or-nothing on bad input.
    for idx, item in enumerate(body.items):
        targets = [
            t for t in (item.series, item.set_id, item.accessions) if t is not None
        ]
        if len(targets) != 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"item {idx}: provide exactly one of series, set_id, "
                        "or accessions"
                    ),
                },
            )

    known = ldb.known_series()
    known_lower = {s.lower() for s in known}
    for idx, item in enumerate(body.items):
        if item.series is not None and item.series.lower() not in known_lower:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"item {idx}: unknown series {item.series!r}",
                    "known_series": known[:50],
                },
            )

    results: list[dict] = []
    for item in body.items:
        reason = item.reason
        if item.source_note:
            reason = f"{reason} [source: {item.source_note}]"
        try:
            if item.series is not None:
                matched = ldb.mark_stale(series=item.series, reason=reason)
                target = {"series": item.series}
            elif item.set_id is not None:
                set_id = _coerce_set_id(item.set_id)
                matched = ldb.mark_stale(set_id=set_id, reason=reason)
                target = {"set_id": item.set_id}
            else:
                matched = ldb.mark_stale(accessions=item.accessions, reason=reason)
                target = {"accessions": item.accessions}
        except UnknownSeries as exc:  # defensive; pre-validated above
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"unknown series {exc.series!r}",
                    "known_series": exc.known,
                },
            ) from exc
        results.append({**target, "reason": reason, "matched": matched})

    return {
        "items": results,
        "total_marked": sum(r["matched"] for r in results),
    }


def _coerce_set_id(raw: str) -> int | str:
    try:
        return int(raw)
    except ValueError:
        return raw
