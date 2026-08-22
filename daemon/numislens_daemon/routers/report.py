"""Appraisal-report endpoints: JSON rollup and printable PDF."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from numislens_core import Ledger, build_appraisal_report
from numislens_core.report import realized_summary

from ..deps import get_ledger
from ..report_pdf import render_appraisal_pdf

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]

# top is validated strictly (ge/le) so out-of-range 422s rather than clamping.
TopParam = Annotated[int, Query(ge=1, le=100)]


@router.get("/report/appraisal", tags=["report"])
def appraisal_json(ldb: LedgerDep, top: TopParam = 10) -> dict:
    # Verbatim core dict: all money is integer cents; the PWA formats client-side.
    return build_appraisal_report(ldb.conn, top_n=top)


@router.get("/portfolio/realized", tags=["report"])
def portfolio_realized(ldb: LedgerDep) -> dict:
    """Realized P&L over sold coins (proceeds minus cost basis).

    Missing inputs are disclosed (``missing_cost_count``), never imputed —
    the no-fabrication rule applies to profit as much as to value.
    """
    return realized_summary(ldb.conn)


@router.get("/report/appraisal.pdf", tags=["report"])
def appraisal_pdf(ldb: LedgerDep, top: TopParam = 10) -> Response:
    report = build_appraisal_report(ldb.conn, top_n=top)
    pdf_bytes = render_appraisal_pdf(report)
    # Filename dates off generated_at (ISO-8601), so YYYY-MM-DD is the leading 10.
    date = report["generated_at"][:10]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="numislens-appraisal-{date}.pdf"',
        },
    )
