"""Set resource endpoints."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from numislens_core import Ledger, validate_manifest

from ..deps import get_ledger
from ..schemas import AssignBody, SetLoad

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


def _parse_set_id(raw: str) -> int | str:
    try:
        return int(raw)
    except ValueError:
        return raw


@router.get("/sets", tags=["sets"])
def list_sets(ldb: LedgerDep) -> list[dict]:
    rows = ldb.conn.execute(
        "SELECT id, set_key, name, series, composition_ref FROM sets ORDER BY id"
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        filled, total = ldb.set_completion(row["id"])
        result.append({**dict(row), "filled": filled, "total": total})
    return result


@router.post("/sets/load", tags=["sets"])
def load_set(body: SetLoad, ldb: LedgerDep) -> dict:
    if (body.manifest_path is None) == (body.manifest is None):
        raise HTTPException(
            status_code=422, detail="provide exactly one of manifest_path or manifest"
        )

    if body.manifest_path is not None:
        set_id = ldb.load_set_manifest(body.manifest_path)
    else:
        validate_manifest(body.manifest)
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        try:
            tmp.write(json.dumps(body.manifest).encode())
            tmp.close()
            set_id = ldb.load_set_manifest(tmp.name)
        finally:
            os.unlink(tmp.name)

    return {"set_id": set_id}


@router.get("/sets/{set_id}/gaps", tags=["sets"])
def set_gaps(set_id: str, ldb: LedgerDep) -> dict:
    sid = _parse_set_id(set_id)
    return {"gaps": ldb.set_gaps(sid)}


@router.get("/sets/{set_id}/status", tags=["sets"])
def set_status(set_id: str, ldb: LedgerDep) -> dict:
    sid = _parse_set_id(set_id)
    filled, total = ldb.set_completion(sid)
    gaps = ldb.set_gaps(sid)
    return {"filled": filled, "total": total, "gaps": len(gaps)}


@router.get("/sets/{set_id}/board", tags=["sets"])
def set_board(set_id: str, ldb: LedgerDep) -> dict:
    sid = _parse_set_id(set_id)
    return ldb.set_board(sid)


@router.post("/sets/{set_id}/assign", tags=["sets"])
def assign_to_set(set_id: str, body: AssignBody, ldb: LedgerDep) -> dict:
    sid = _parse_set_id(set_id)
    ldb.assign_to_slot(sid, body.slot.model_dump(exclude_none=True), body.accession)
    filled, total = ldb.set_completion(sid)
    return {"assigned": body.accession, "filled": filled, "total": total}
