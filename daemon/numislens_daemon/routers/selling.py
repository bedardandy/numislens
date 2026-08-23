"""Sell-prep endpoints: per-coin listing kits and a staging listings CSV."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from numislens_core import Ledger
from numislens_core.listing import (
    build_listing_description,
    build_listing_title,
    listing_row,
    listings_csv,
)

from ..deps import get_ledger

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


@router.get("/coins/{accession}/listing-kit.zip", tags=["selling"])
def listing_kit(accession: str, request: Request, ldb: LedgerDep) -> Response:
    """Everything a marketplace listing needs, in one zip.

    listing.txt (deterministic title + description from ledger facts only),
    the stored photos, and metadata.json (full record + append-only
    appraisal trail with source citations). Absent facts are omitted, never
    padded — the kit states what the ledger knows and nothing more.
    """
    coin = ldb.get_coin(accession)
    if coin is None:
        raise HTTPException(status_code=404, detail=f"coin not found: {accession}")

    appraisals = ldb.list_appraisals(accession)
    images = ldb.list_images(accession)
    title = build_listing_title(coin)
    description = build_listing_description(coin, appraisals)

    buf = io.BytesIO()
    manifest_images: list[dict] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("listing.txt", f"{title}\n\n{description}\n")
        images_dir = Path(request.app.state.images_dir)
        for img in images:
            path = Path(img["path"])
            entry = {"kind": img["kind"], "content_hash": img["content_hash"]}
            if path.is_file():
                arcname = f"images/{img['kind']}-{img['content_hash'][:8]}{path.suffix or '.jpg'}"
                zf.write(path, arcname)
                entry["file"] = arcname
            else:
                entry["file"] = None
                entry["error"] = "file missing on disk"
            manifest_images.append(entry)
        metadata = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coin": coin,
            "appraisals": appraisals,
            "images": manifest_images,
        }
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="numislens-listing-{accession}.zip"'
            ),
        },
    )


@router.get("/export/listings.csv", tags=["selling"])
def export_listings(ldb: LedgerDep, disposition: str = "for_sale") -> Response:
    """Staging CSV for marketplace upload, one row per coin in a disposition.

    Defaults to for_sale (sell-prep is the point); pass any valid disposition.
    Column NAMES follow eBay's bulk-listing template where stable, but no
    taxonomy IDs are invented — verify the mapping against your template
    before upload. StartPrice falls back to cost basis when no estimate
    exists; an EMPTY StartPrice means the seller must set one.
    """
    coins = ldb.find_coins(disposition=disposition)
    rows = []
    for coin in coins:
        accession = coin["accession_no"]
        rows.append(
            listing_row(
                coin,
                description=build_listing_description(
                    coin, ldb.list_appraisals(accession)
                ),
                image_count=len(ldb.list_images(accession)),
            )
        )
    date = datetime.now(timezone.utc).isoformat()[:10]
    return Response(
        content=listings_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="numislens-listings-{date}.csv"'
            ),
        },
    )
