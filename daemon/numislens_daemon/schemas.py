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


class CoinIdentify(StrictModel):
    # Phase-4 vision writeback: fill NULL identification fields on an existing
    # coin. The daemon/core fill NULL-only and never overwrite (see
    # Ledger.update_identification); non-null fields are reported skipped. This
    # is the one endpoint that legitimately sets grade_bucket outside coin
    # creation — grade_source records that a photo pipeline produced it.
    series: Optional[str] = None
    year: Optional[int] = None
    mintmark: Optional[str] = None
    denomination: Optional[str] = None
    country: Optional[str] = None
    composition_id: Optional[int] = None
    grade_bucket: Optional[str] = None
    grade_source: Optional[str] = None


class CoinEdit(StrictModel):
    # Human corrections to an existing coin (PUT). Every field is optional;
    # a field PRESENT with null CLEARS it (an explicit, event-logged
    # correction). Grade fields are deliberately absent — grade changes flow
    # through /appraise or the vision writeback so provenance stays
    # append-only. Unknown fields 422 (invariant 8).
    series: Optional[str] = None
    year: Optional[int] = None
    mintmark: Optional[str] = None
    denomination: Optional[str] = None
    country: Optional[str] = None
    composition_id: Optional[int] = None
    weight_g: Optional[float] = None
    diameter_mm: Optional[float] = None
    tpg_cert: Optional[str] = None
    cost_basis_cents: Optional[int] = Field(
        default=None, description="Cost basis in cents (integer); null clears."
    )
    acquired_date: Optional[str] = None
    acquired_source: Optional[str] = None
    value_est_cents: Optional[int] = Field(
        default=None, description="Estimated value in cents (integer); null clears."
    )
    value_basis: Optional[str] = Field(
        default=None,
        description="melt | numismatic | hybrid; null clears.",
    )
    appraisal_confidence: Optional[float] = None
    location_id: Optional[int] = Field(
        default=None, description="Location id; null clears."
    )
    notes: Optional[str] = None


class QuickAddBody(StrictModel):
    text: str = Field(
        description="Free-text coin capture, e.g. '1943 steel cent, box 3 slot 12, paid $4'."
    )


class MoveBody(StrictModel):
    location_id: int
    expected_from_location_id: Optional[int] = Field(
        default=None,
        description='Optimistic concurrency: fail with 409 if the coin is no longer at this location.',
    )


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


class DigestItem(StrictModel):
    # A single distilled market-digest finding. Provide EXACTLY ONE target:
    # series (case-insensitive exact match), set_id (id or set_key), or an
    # explicit accessions list. reason is required; source_note carries the
    # citation (headline/auction/URL) and is folded into the stored reason.
    series: Optional[str] = None
    set_id: Optional[str] = None
    accessions: Optional[list[str]] = None
    reason: str = Field(description="Why these coins may have moved (required).")
    source_note: Optional[str] = Field(
        default=None,
        description="Citation for the finding (headline, auction record, URL).",
    )


class DigestBody(StrictModel):
    items: list[DigestItem] = Field(
        description="Distilled findings; each marks its target coins stale."
    )


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
