"""Pydantic request body schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    # Unknown fields must 422, not vanish: assistant callers guess field
    # names (e.g. "mint" for "mintmark") and silent drops lose data.
    model_config = ConfigDict(extra="forbid")


class CoinCreate(StrictModel):
    series: Optional[str] = None
    year: Optional[int] = None
    mintmark: Optional[str] = None
    denomination: Optional[str] = None
    country: Optional[str] = None
    composition_id: Optional[int] = None
    weight_g: Optional[float] = None
    diameter_mm: Optional[float] = None
    grade_bucket: Optional[str] = None
    grade_source: Optional[str] = None
    tpg_cert: Optional[str] = None
    cost_basis_cents: Optional[int] = Field(
        default=None, description="Cost basis in cents (integer)."
    )
    acquired_date: Optional[str] = None
    acquired_source: Optional[str] = None
    value_est_cents: Optional[int] = Field(
        default=None, description="Estimated value in cents (integer)."
    )
    value_basis: Optional[str] = None
    appraisal_confidence: Optional[float] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None


class MoveBody(StrictModel):
    location_id: int


class AppraiseBody(StrictModel):
    appraised_by: str
    grade_bucket: Optional[str] = None
    value_cents: Optional[int] = Field(
        default=None, description="Appraised value in cents (integer)."
    )
    value_basis: Optional[str] = None
    rationale: Optional[str] = None
    token_cost: Optional[int] = Field(
        default=None, description="Token cost in cents (integer)."
    )
    confidence: Optional[float] = None


class LocationCreate(StrictModel):
    kind: str
    label: str
    parent_id: Optional[int] = None


class SlotSpec(StrictModel):
    year: int
    mint: str
    note: Optional[str] = None


class AssignBody(StrictModel):
    slot: SlotSpec
    accession: str


class SetLoad(StrictModel):
    manifest_path: Optional[str] = None
    manifest: Optional[dict] = None
