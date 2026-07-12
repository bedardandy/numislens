"""Label-sheet PDF endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from numislens_core import Ledger

from ..deps import get_ledger
from ..labels import render_labels

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


@router.get("/labels.pdf", tags=["labels"])
def labels_pdf(
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

    # QR encodes numislens://c/<accession>; the PWA route /c/<accession> is delivered in Phase 3.
    pdf_bytes = render_labels(coins)
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="numislens-labels.pdf"',
        },
    )
