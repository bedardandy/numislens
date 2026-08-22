"""Data portability endpoints: CSV export and strict all-or-nothing import."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from numislens_core import Ledger
from numislens_core.csvio import (
    CsvImportError,
    coin_to_csv_row,
    coins_to_csv,
    parse_coins_csv,
)

from ..deps import get_ledger

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


def _composition_maps(ldb: Ledger) -> tuple[dict[int, str], dict[str, int]]:
    by_id: dict[int, str] = {}
    by_name: dict[str, int] = {}
    for comp in ldb.list_compositions():
        by_id[comp["id"]] = comp["name"]
        by_name[comp["name"].lower()] = comp["id"]
    return by_id, by_name


def _location_paths(ldb: Ledger) -> dict[str, int]:
    rows = ldb.conn.execute("SELECT id FROM locations ORDER BY id").fetchall()
    return {ldb.location_path(row["id"]).lower(): row["id"] for row in rows}


@router.get("/export/coins.csv", tags=["data"])
def export_coins_csv(ldb: LedgerDep) -> Response:
    """Every coin as CSV — stable columns, integer cents, composition by name,
    location by path. ``accession_no`` is informational on import (ignored)."""
    comps_by_id, _ = _composition_maps(ldb)
    rows = []
    for coin in ldb.find_coins():
        location_path = (
            ldb.location_path(coin["location_id"])
            if coin.get("location_id") is not None
            else None
        )
        rows.append(
            coin_to_csv_row(
                coin,
                composition_name=comps_by_id.get(coin.get("composition_id")),
                location_path=location_path,
            )
        )
    date = datetime.now(timezone.utc).isoformat()[:10]
    return Response(
        content=coins_to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="numislens-coins-{date}.csv"',
        },
    )


@router.post("/import/coins.csv", tags=["data"])
def import_coins_csv(ldb: LedgerDep, file: UploadFile) -> dict:
    """Bulk-add coins from a CSV exported by (or shaped like) this endpoint.

    Strict all-or-nothing: every row is validated before anything is created;
    any problem returns 422 with every row error listed and an unchanged
    ledger. ``accession_no`` is ignored (server-assigned); unknown locations/
    compositions are errors, never auto-created.
    """
    if file.content_type not in (None, "", "text/csv", "application/csv",
                                 "application/vnd.ms-excel"):
        raise HTTPException(
            status_code=422, detail=f"expected text/csv, got {file.content_type}"
        )
    # Sync endpoint + sync get_ledger dependency share one worker thread, so
    # the spooled upload is read synchronously (no await) — same as images.
    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")  # tolerate Excel's BOM
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 text")

    try:
        batches = parse_coins_csv(
            text,
            composition_ids_by_name=_composition_maps(ldb)[1],
            location_ids_by_path=_location_paths(ldb),
        )
    except CsvImportError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.errors},
        ) from exc

    created: list[str] = []
    try:
        for fields in batches:
            # Disposition is applied via the lifecycle API after creation —
            # it keeps its own validation and writes its own event.
            sold_fields = {
                k: fields.pop(k)
                for k in ("sold_date", "sold_price_cents", "sold_venue")
                if k in fields
            }
            disposition = fields.pop("disposition", None)
            accession = ldb.add_coin(**fields)
            if disposition is not None:
                ldb.set_disposition(
                    accession, disposition, **sold_fields
                )
            created.append(accession)
    except ValueError as exc:  # defensive: csvio pre-validates everything above
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"created": created, "count": len(created)}
