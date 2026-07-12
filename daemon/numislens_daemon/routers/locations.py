"""Location resource endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from numislens_core import Ledger

from ..deps import get_ledger
from ..schemas import LocationCreate
from ..serializers import serialize_coin

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


def _build_tree(rows: list) -> list[dict]:
    by_id: dict[int, dict] = {}
    for row in rows:
        by_id[row["id"]] = {
            "id": row["id"],
            "kind": row["kind"],
            "label": row["label"],
            "children": [],
        }
    roots: list[dict] = []
    for row in rows:
        node = by_id[row["id"]]
        parent_id = row["parent_id"]
        if parent_id is None:
            roots.append(node)
        else:
            by_id[parent_id]["children"].append(node)
    return roots


@router.post("/locations", tags=["locations"])
def create_location(body: LocationCreate, ldb: LedgerDep) -> dict:
    lid = ldb.create_location(body.kind, body.label, parent=body.parent_id)
    return {"id": lid, "path": ldb.location_path(lid)}


@router.get("/locations/tree", tags=["locations"])
def location_tree(ldb: LedgerDep) -> dict:
    rows = ldb.conn.execute(
        "SELECT id, parent_id, kind, label FROM locations ORDER BY id"
    ).fetchall()
    return {"tree": _build_tree(rows)}


@router.get("/locations/{location_id}", tags=["locations"])
def get_location(
    location_id: int,
    ldb: LedgerDep,
    recursive: bool = True,
) -> dict:
    path = ldb.location_path(location_id)
    contents = [
        serialize_coin(c) for c in ldb.contents(location_id, recursive=recursive)
    ]
    return {
        "id": location_id,
        "path": path,
        "recursive": recursive,
        "contents": contents,
    }
