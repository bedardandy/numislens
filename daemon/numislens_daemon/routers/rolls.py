"""Coin-roll endpoints (bulk holdings).

Thin HTTP layer over ``numislens_core.rolls`` (a pure connection-based module).
RollNotFound maps to 404 and any other RollError to 422, mirroring how the
shared error handlers map the ledger's not-found vs validation errors -- but
handled inline here because RollError is not a LedgerError subclass and this
router owns the mapping.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from numislens_core import Ledger, rolls
from numislens_core.rolls import RollError, RollNotFound
from pydantic import BaseModel, ConfigDict, Field

from ..deps import get_ledger
from ..quickadd import parse_quick_add

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]


class RollCreateBody(BaseModel):
    # Unknown fields must 422, not vanish (assistant callers guess names).
    model_config = ConfigDict(extra="forbid")

    denomination: str
    count: int = Field(description="Number of coins in the roll (>= 1).")
    country: Optional[str] = None
    series: Optional[str] = None
    year: Optional[int] = None
    composition_name: Optional[str] = None
    variant: Optional[str] = None
    cost_basis_cents: Optional[int] = Field(
        default=None, description="Cost basis in cents (integer)."
    )
    acquired_date: Optional[str] = None
    acquired_source: Optional[str] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None


class RollPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None
    variant: Optional[str] = None


class RollPullBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(description="Number of coins to pull out of the roll (>= 1).")
    quick: Optional[list[str]] = Field(
        default=None,
        description=(
            "Optional free-text captures (len <= count); each is run through the "
            "quick-add parser to create a real coin row, acquired_source=roll_no."
        ),
    )


@router.post("/rolls", status_code=status.HTTP_201_CREATED, tags=["rolls"])
def create_roll(body: RollCreateBody, ldb: LedgerDep) -> dict:
    kwargs = body.model_dump(exclude_unset=True, exclude_none=True)
    denomination = kwargs.pop("denomination")
    count = kwargs.pop("count")
    try:
        return rolls.create_roll(ldb.conn, denomination, count, **kwargs)
    except RollError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/rolls", tags=["rolls"])
def list_rolls(ldb: LedgerDep, status: Optional[str] = None) -> list[dict]:
    return rolls.list_rolls(ldb.conn, status=status)


@router.get("/rolls/{roll_no}", tags=["rolls"])
def get_roll(roll_no: str, ldb: LedgerDep) -> dict:
    roll = rolls.get_roll(ldb.conn, roll_no)
    if roll is None:
        raise HTTPException(status_code=404, detail=f"roll not found: {roll_no}")
    return roll


@router.patch("/rolls/{roll_no}", tags=["rolls"])
def update_roll(roll_no: str, body: RollPatchBody, ldb: LedgerDep) -> dict:
    try:
        return rolls.update_roll(
            ldb.conn, roll_no, **body.model_dump(exclude_unset=True)
        )
    except RollNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RollError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/rolls/{roll_no}/pull", tags=["rolls"])
def pull_roll(roll_no: str, body: RollPullBody, ldb: LedgerDep) -> dict:
    quick = body.quick or []
    if len(quick) > body.count:
        raise HTTPException(
            status_code=422,
            detail=f"quick list ({len(quick)}) longer than pull count ({body.count})",
        )

    # Parse every quick string BEFORE mutating anything so an unparseable
    # capture fails loud (422) without half-pulling the roll.
    series_names = [
        r["series"]
        for r in ldb.conn.execute(
            "SELECT DISTINCT series FROM sets WHERE series IS NOT NULL"
        ).fetchall()
    ]
    locations = [
        dict(r)
        for r in ldb.conn.execute(
            "SELECT id, parent_id, kind, label FROM locations"
        ).fetchall()
    ]
    compositions = ldb.list_compositions()
    parsed_coins: list[dict] = []
    for text in quick:
        result = parse_quick_add(
            text,
            compositions=compositions,
            series_names=series_names,
            locations=locations,
        )
        parsed = result["parsed"]
        if "series" not in parsed and "year" not in parsed:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        "could not identify a coin from quick text: need at "
                        "least a series or a 4-digit year"
                    ),
                    "text": text,
                    "parsed": parsed,
                    "unresolved": result["unresolved"],
                },
            )
        parsed_coins.append(parsed)

    try:
        roll = rolls.pull_from_roll(ldb.conn, roll_no, body.count)
    except RollNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RollError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    coins_created: list[str] = []
    for parsed in parsed_coins:
        parsed = {**parsed, "acquired_source": roll_no}
        coins_created.append(ldb.add_coin(**parsed))

    return {"roll": roll, "coins_created": coins_created}
