"""Coin resource endpoints."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from numislens_core import Ledger
from PIL import Image

from ..deps import get_ledger
from ..quickadd import parse_quick_add
from ..schemas import (
    AppraiseBody,
    CoinCreate,
    CoinEdit,
    CoinIdentify,
    DispositionBody,
    MoveBody,
    QuickAddBody,
)
from ..serializers import serialize_coin

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]

# Upload hardening: a strict content-type ALLOWLIST (no image/* wildcard —
# e.g. image/svg+xml is scriptable and heic renders inconsistently), a size
# cap, and re-encode-on-store. Re-encoding through Pillow drops EXIF metadata
# (phone photos carry GPS coordinates — these images are meant to be shared or
# listed publicly later) and bounds stored dimensions.
ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per uploaded image
MAX_IMAGE_EDGE = 1600  # px; longest edge after downscale (aspect preserved)

_FORMAT_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_CHUNK = 1 << 20


def _read_capped(upload: UploadFile, kind: str) -> bytes:
    buf = io.BytesIO()
    while True:
        chunk = upload.file.read(_CHUNK)
        if not chunk:
            break
        buf.write(chunk)
        if buf.tell() > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{kind}: image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit",
            )
    return buf.getvalue()


def _reencode_stripped(data: bytes, kind: str) -> tuple[bytes, str]:
    """Decode-validate, downscale, and re-encode an uploaded image.

    Returns (processed_bytes, file_extension). Decoding validates that the
    bytes really are an image regardless of the client-declared content type;
    re-saving without an EXIF block strips all metadata; oversized longest
    edges are downscaled with aspect preserved.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(
            status_code=422, detail=f"{kind}: not a decodable image"
        )
    fmt = (img.format or "").upper()
    ext = _FORMAT_EXT.get(fmt)
    if ext is None:
        raise HTTPException(
            status_code=422,
            detail=f"{kind}: unsupported image format: {fmt or 'unknown'} "
                    "(allowed: JPEG, PNG, WEBP)",
        )
    if max(img.size) > MAX_IMAGE_EDGE:
        img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
    # JPEG cannot store alpha/palette modes; flatten onto white like a scan.
    if fmt == "JPEG" and img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format=fmt)  # no exif/icc kwargs => metadata dropped
    return out.getvalue(), ext


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
    Any leftover input text no extractor consumed (unknown words, extra year
    tokens beyond the first) is echoed back in ``unresolved`` as
    ``unrecognized: "..."`` entries, so nothing is silently dropped.
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
    response: Response,
    series: str | None = None,
    year: int | None = None,
    mintmark: str | None = None,
    denomination: str | None = None,
    grade_bucket: str | None = None,
    composition_id: int | None = None,
    location_id: int | None = None,
    disposition: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict | None]:
    """List coins. The body stays a bare array (backward compatible); the
    total matching count rides in ``X-Total-Count`` for paging clients."""
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
            "disposition": disposition,
        }.items()
        if v is not None
    }
    response.headers["X-Total-Count"] = str(ldb.count_coins(**filters))
    results = ldb.find_coins(limit=limit, offset=offset, **filters)
    return [serialize_coin(c) for c in results]


@router.get("/duplicates", tags=["data"])
def list_duplicates(ldb: LedgerDep) -> list[dict]:
    """Candidate duplicate identities (same series+year+mintmark).

    Read-only suspect list for inherited-collection triage: double entries
    surface with their locations; adjudication is human work.
    """
    return ldb.find_duplicates()


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
    # Append-only appraisal trail (newest first). Lets the vision worker detect
    # a prior vision:* appraisal and skip re-processing under --pending, and
    # surfaces the provenance to any surface that wants it.
    result["appraisals"] = ldb.list_appraisals(accession)
    return result


@router.patch("/coins/{accession}", tags=["coins"])
def identify_coin(accession: str, body: CoinIdentify, ldb: LedgerDep) -> dict:
    """Fill NULL identification fields on an existing coin (Phase-4 writeback).

    Fill-NULL-ONLY: any field the coin already has is left untouched and
    reported in ``skipped`` — a vision pass never overwrites a user/human
    identity or grade. This is the sole endpoint that sets ``grade_bucket``
    outside coin creation, and only with a ``grade_source`` recording that a
    photo pipeline produced it. Returns ``{written, skipped, coin}``.
    """
    result = ldb.update_identification(
        accession, **body.model_dump(exclude_unset=True)
    )
    result["coin"] = serialize_coin(ldb.get_coin(accession))
    return result


@router.put("/coins/{accession}", tags=["coins"])
def edit_coin(accession: str, body: CoinEdit, ldb: LedgerDep) -> dict:
    """Apply a human correction to a coin (distinct from the vision PATCH).

    Every provided field overwrites (including clearing via null); each change
    is logged to the append-only events table with its before/after. Grade
    fields are not editable here — grade changes go through /appraise or the
    vision writeback so provenance stays append-only. Returns
    ``{changed: {field: [before, after]}, coin}``.
    """
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=422,
            detail="no fields to edit: provide at least one field",
        )
    result = ldb.edit_coin(accession, **fields)
    if "coin" in result:
        result["coin"] = serialize_coin(result["coin"])
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


@router.post("/coins/{accession}/disposition", tags=["coins"])
def set_disposition(accession: str, body: DispositionBody, ldb: LedgerDep) -> dict:
    """Move a coin through owned -> for_sale -> sold (or discarded).

    Marking sold requires ``sold_price_cents`` (0 = a giveaway — a real
    outcome, not an unknown). Every transition appends a 'disposition' event;
    non-sold states clear the sold_* fields. Returns the fresh coin row.
    """
    coin = ldb.set_disposition(
        accession,
        body.disposition,
        sold_date=body.sold_date,
        sold_price_cents=body.sold_price_cents,
        sold_venue=body.sold_venue,
    )
    return serialize_coin(coin)


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
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"{kind}: unsupported content-type: {upload.content_type} "
                        "(allowed: image/jpeg, image/png, image/webp)",
            )
        # Sync endpoint + sync get_ledger dependency run in the same worker
        # thread, so the SQLite connection is used from its creating thread.
        # Read the underlying spooled file synchronously (no await).
        data = _read_capped(upload, kind)
        processed, ext = _reencode_stripped(data, kind)
        digest = hashlib.sha256(processed).hexdigest()
        dest = images_dir / f"{digest}.{ext}"
        if not dest.exists():
            dest.write_bytes(processed)
        rec = ldb.add_image(accession, kind, digest, str(dest))
        results.append(rec)

    return {"images": results}
