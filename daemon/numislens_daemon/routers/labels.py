"""Label-sheet PDF endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from numislens_core import Ledger, rolls

from ..deps import get_ledger
from ..labels import render_labels, render_roll_labels

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


@router.get("/labels.pdf", tags=["labels"])
def labels_pdf(
    request: Request,
    ldb: LedgerDep,
    location_id: Optional[int] = None,
    accessions: Optional[str] = None,
) -> Response:
    if (location_id is None) == (accessions is None):
        raise HTTPException(
            422, "provide exactly one of location_id or accessions"
        )

    if location_id is not None:
        coins = ldb.contents(location_id, recursive=True)
    else:
        acc_list = [a.strip() for a in accessions.split(",") if a.strip()]
        if not acc_list:
            raise HTTPException(422, "no accessions provided")
        coins = []
        for a in acc_list:
            coin = ldb.get_coin(a)
            if coin is None:
                raise HTTPException(404, f"coin not found: {a}")
            coins.append(coin)

    # QR deep links resolve via the PWA /c/<accession> route. Prefer a stable
    # public base (Tailscale name) over whatever host this request came in on.
    base_url = os.environ.get("NUMISLENS_PUBLIC_URL") or str(request.base_url)
    pdf_bytes = render_labels(coins, base_url=base_url)
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="numislens-labels.pdf"',
        },
    )


@router.get("/labels/rolls.pdf", tags=["labels"])
def roll_labels_pdf(
    request: Request,
    ldb: LedgerDep,
    rolls_param: Optional[list[str]] = Query(default=None, alias="rolls"),
) -> Response:
    """Avery 5160 sheet of roll labels. ``?rolls=NR-...&rolls=...`` (repeatable)
    selects specific rolls; omitted selects every non-exhausted roll."""
    if rolls_param:
        selected = []
        for roll_no in rolls_param:
            roll = rolls.get_roll(ldb.conn, roll_no)
            if roll is None:
                raise HTTPException(404, f"roll not found: {roll_no}")
            selected.append(roll)
    else:
        selected = [
            r
            for r in rolls.list_rolls(ldb.conn)
            if r["status"] != "exhausted"
        ]

    base_url = os.environ.get("NUMISLENS_PUBLIC_URL") or str(request.base_url)
    pdf_bytes = render_roll_labels(selected, base_url=base_url)
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="numislens-roll-labels.pdf"',
        },
    )
