"""Coin resource endpoints."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from numislens_core import Ledger

from ..deps import get_ledger
from ..quickadd import parse_quick_add
from ..schemas import AppraiseBody, CoinCreate, MoveBody, QuickAddBody
from ..serializers import serialize_coin

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


@router.post("/coins", status_code=status.HTTP_201_CREATED, tags=["coins"])
def create_coin(body: CoinCreate, ldb: LedgerDep) -> dict | None:
    accession = ldb.add_coin(**body.model_dump(exclude_unset=True, exclude_none=True))
    return serialize_coin(ldb.get_coin(accession))


@router.post("/coins/quick", tags=["coins"])
def quick_add_coin(body: QuickAddBody, ldb: LedgerDep) -> dict:
    """Deterministically parse free text and create a coin if it is safe to.

    NO LLM, NO guessing. The coin is created only when at least a series or a
    year parsed cleanly; otherwise this responds 422 with what it did and did
    not understand. Composition is set only by numismatically CERTAIN rules;
    grade is never parsed. Unmapped phrases (unknown locations, uncertain
    compositions, malformed money) are returned in ``unresolved`` — a mentioned
    location that does not already exist is listed there, NOT auto-created.
    """
    series_names = [
        row["series"]
        for row in ldb.conn.execute(
            "SELECT DISTINCT series FROM sets WHERE series IS NOT NULL"
        ).fetchall()
    ]
    locations = [
        dict(row)
        for row in ldb.conn.execute(
            "SELECT id, parent_id, kind, label FROM locations"
        ).fetchall()
    ]
    result = parse_quick_add(
        body.text,
        compositions=ldb.list_compositions(),
        series_names=series_names,
        locations=locations,
    )
    parsed = result["parsed"]
    unresolved = result["unresolved"]

    # Fail-loud contract: never guess. Require at least a series or a year.
    if "series" not in parsed and "year" not in parsed:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "could not identify a coin: need at least a series or a "
                    "4-digit year"
                ),
                "parsed": parsed,
                "unresolved": unresolved,
            },
        )

    accession = ldb.add_coin(**parsed)
    return {
        "parsed": parsed,
        "unresolved": unresolved,
        "created": accession,
        "coin": serialize_coin(ldb.get_coin(accession)),
    }


@router.get("/coins", tags=["coins"])
def list_coins(
    ldb: LedgerDep,
    series: str | None = None,
    year: int | None = None,
    mintmark: str | None = None,
    denomination: str | None = None,
    grade_bucket: str | None = None,
    composition_id: int | None = None,
    location_id: int | None = None,
) -> list[dict | None]:
    filters = {
        k: v
        for k, v in {
            "series": series,
            "year": year,
            "mintmark": mintmark,
            "denomination": denomination,
            "grade_bucket": grade_bucket,
            "composition_id": composition_id,
            "location_id": location_id,
        }.items()
        if v is not None
    }
    results = ldb.find_coins(**filters)
    return [serialize_coin(c) for c in results]


@router.get("/compositions", tags=["coins"])
def get_compositions(ldb: LedgerDep) -> list[dict]:
    return ldb.list_compositions()


@router.get("/coins/{accession}", tags=["coins"])
def get_coin(accession: str, ldb: LedgerDep) -> dict | None:
    coin = ldb.get_coin(accession)
    if coin is None:
        raise HTTPException(status_code=404, detail=f"coin not found: {accession}")
    result = serialize_coin(coin)
    # Expose image metadata (kind + content_hash) so the PWA can build image
    # URLs; the on-disk path is intentionally NOT leaked to clients.
    result["coin_images"] = [
        {"kind": img["kind"], "content_hash": img["content_hash"]}
        for img in ldb.list_images(accession)
    ]
    return result


@router.get("/coins/{accession}/images/{content_hash}", tags=["coins"])
def get_coin_image(
    accession: str, content_hash: str, ldb: LedgerDep
) -> FileResponse:
    # list_images raises CoinNotFound (-> 404) if the coin is unknown.
    images = ldb.list_images(accession)
    match = next(
        (img for img in images if img["content_hash"] == content_hash), None
    )
    if match is None:
        raise HTTPException(
            status_code=404, detail=f"image not found: {content_hash}"
        )
    path = Path(match["path"])
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"image file missing on disk: {content_hash}"
        )
    return FileResponse(path)


@router.post("/coins/{accession}/move", tags=["coins"])
def move_coin(accession: str, body: MoveBody, ldb: LedgerDep) -> dict | None:
    ldb.move_coin(accession, body.location_id, expected_from=body.expected_from_location_id)
    return serialize_coin(ldb.get_coin(accession))


@router.post("/coins/{accession}/appraise", tags=["coins"])
def appraise_coin(accession: str, body: AppraiseBody, ldb: LedgerDep) -> dict:
    appraisal_kwargs = {
        k: v
        for k, v in body.model_dump(exclude={"appraised_by"}).items()
        if v is not None
    }
    appraisal_id = ldb.record_appraisal(
        accession, body.appraised_by, **appraisal_kwargs
    )
    return {
        "appraisal_id": appraisal_id,
        "coin": serialize_coin(ldb.get_coin(accession)),
    }


@router.post("/coins/{accession}/images", tags=["coins"])
def upload_coin_images(
    accession: str,
    request: Request,
    ldb: LedgerDep,
    obverse: UploadFile | None = File(None),
    reverse: UploadFile | None = File(None),
    edge: UploadFile | None = File(None),
    slab: UploadFile | None = File(None),
) -> dict:
    if ldb.get_coin(accession) is None:
        raise HTTPException(status_code=404, detail=f"coin not found: {accession}")

    images_dir = Path(request.app.state.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for kind, upload in (
        ("obverse", obverse),
        ("reverse", reverse),
        ("edge", edge),
        ("slab", slab),
    ):
        if upload is None:
            continue
        if upload.content_type is None or not upload.content_type.startswith("image/"):
            raise HTTPException(
                status_code=422,
                detail=f"{kind}: not an image content-type: {upload.content_type}",
            )
        # Sync endpoint + sync get_ledger dependency run in the same worker
        # thread, so the SQLite connection is used from its creating thread.
        # Read the underlying spooled file synchronously (no await).
        data = upload.file.read()
        digest = hashlib.sha256(data).hexdigest()
        ext = _CONTENT_TYPE_EXT.get(
            upload.content_type, upload.content_type.split("/")[-1]
        )
        dest = images_dir / f"{digest}.{ext}"
        if not dest.exists():
            dest.write_bytes(data)
        rec = ldb.add_image(accession, kind, digest, str(dest))
        results.append(rec)

    return {"images": results}
