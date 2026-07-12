from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .client import NumisLensClient, NumisLensError
from .config import load_config

mcp = FastMCP("numislens_mcp")


def _client() -> NumisLensClient:
    return NumisLensClient(load_config())


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _body(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


@mcp.tool(
    name="find_coins",
    annotations={
        "title": "Find Coins",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def find_coins(
    series: Optional[str] = None,
    year: Optional[int] = None,
    mintmark: Optional[str] = None,
    location_id: Optional[int] = None,
) -> str:
    """Search the collection ledger for coins matching optional filters.

    ``location_id`` filters recursively by the
    location subtree (cabinet, box, tray, slot, etc.).

    Returns a JSON array of coin records. Money fields are integer cents with
    companion ``*_display`` strings (e.g. ``"$5.00"``) for human reading.
    """
    try:
        params: dict[str, Any] = {}
        if series is not None:
            params["series"] = series
        if year is not None:
            params["year"] = year
        if mintmark is not None:
            params["mintmark"] = mintmark
        if location_id is not None:
            params["location_id"] = location_id
        result = await _client().request_json("GET", "/api/v1/coins", params=params or None)
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="get_coin",
    annotations={
        "title": "Get Coin",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_coin(accession: str) -> str:
    """Fetch a single coin record by accession number.

    Accession format is like ``NL-000123``. A missing coin surfaces a 404 error
    with detail ``coin not found``.
    """
    try:
        result = await _client().request_json("GET", f"/api/v1/coins/{accession}")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="add_coin",
    annotations={
        "title": "Add Coin",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def add_coin(
    series: Optional[str] = None,
    year: Optional[int] = None,
    mintmark: Optional[str] = None,
    denomination: Optional[str] = None,
    country: Optional[str] = None,
    composition_id: Optional[int] = None,
    weight_g: Optional[float] = None,
    diameter_mm: Optional[float] = None,
    grade_bucket: Optional[str] = None,
    grade_source: Optional[str] = None,
    tpg_cert: Optional[str] = None,
    cost_basis_cents: Optional[int] = None,
    acquired_date: Optional[str] = None,
    acquired_source: Optional[str] = None,
    value_est_cents: Optional[int] = None,
    value_basis: Optional[str] = None,
    appraisal_confidence: Optional[float] = None,
    location_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> str:
    """Add a new coin to the collection ledger.

    All money values are integer cents (e.g. 500 = $5.00); responses also
    include ``*_display`` strings like ``"$5.00"`` for humans. Money fields
    ``cost_basis_cents`` and ``value_est_cents`` are INTEGER CENTS — never pass
    dollar floats.

    The API rejects unknown fields with HTTP 422, so use these exact field names
    (e.g. ``mintmark``, not ``mint``). Confirm the year and mintmark before
    adding — key dates matter enormously (1914 vs 1914-D can differ ~100x in
    value). Do not invent a ``grade_bucket``; leave it null unless it came from
    a photo or appraisal.

    Returns the created coin record including its new accession number.
    """
    try:
        body = _body(
            series=series,
            year=year,
            mintmark=mintmark,
            denomination=denomination,
            country=country,
            composition_id=composition_id,
            weight_g=weight_g,
            diameter_mm=diameter_mm,
            grade_bucket=grade_bucket,
            grade_source=grade_source,
            tpg_cert=tpg_cert,
            cost_basis_cents=cost_basis_cents,
            acquired_date=acquired_date,
            acquired_source=acquired_source,
            value_est_cents=value_est_cents,
            value_basis=value_basis,
            appraisal_confidence=appraisal_confidence,
            location_id=location_id,
            notes=notes,
        )
        result = await _client().request_json("POST", "/api/v1/coins", json=body)
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="quick_add",
    annotations={
        "title": "Quick Add Coin",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def quick_add(text: str) -> str:
    """Add a coin from one free-text phrase, parsed DETERMINISTICALLY (no LLM).

    Pass natural text like ``"1943 steel cent, box 3 slot 12, paid $4"`` or
    ``"add 1885 Morgan dollar CC to tray 2"``. The daemon extracts year,
    mintmark, series, denomination, cost (integer cents), a numismatically
    CERTAIN composition, and an EXISTING location — it never guesses.

    CONTRACT — always read the response's ``unresolved`` array and relay it to
    the user. It lists anything recognized but not mapped: a location that does
    not already exist (it is NOT auto-created — create it first, then re-add or
    move the coin), an uncertain composition, or a malformed amount. It ALSO
    echoes back any leftover text the parser could not consume as
    ``unrecognized: "..."`` entries (unknown words, a second year token, a
    floating mint letter) — relay those too so the user knows exactly what was
    ignored. If neither a series nor a year could be parsed the call returns a
    422 error describing what was and was not understood, and NO coin is
    created. Grade is never parsed. The response is
    ``{parsed, unresolved, created, coin}`` where ``created`` is the new
    accession number (or the call errored).
    """
    try:
        result = await _client().request_json(
            "POST", "/api/v1/coins/quick", json={"text": text}
        )
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="move_coin",
    annotations={
        "title": "Move Coin",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def move_coin(accession: str, location_id: int) -> str:
    """Record that a coin was physically moved to a new location.

    Call this immediately after moving a coin in the real world. Every coin has
    exactly one location at a time. Returns the updated coin record.
    """
    try:
        result = await _client().request_json(
            "POST",
            f"/api/v1/coins/{accession}/move",
            json={"location_id": location_id},
        )
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="locate_coin",
    annotations={
        "title": "Locate Coin",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def locate_coin(accession: str) -> str:
    """Answer "where is my coin?" with a human-readable location path.

    Returns a path string like ``Cabinet A > Box B2 > Tray 3 > Slot 14``, or a
    plain message if the coin has no location on record.
    """
    try:
        coin = await _client().request_json("GET", f"/api/v1/coins/{accession}")
        location_id = coin.get("location_id")
        if location_id is None:
            return f"{accession} has no location on record."
        location = await _client().request_json("GET", f"/api/v1/locations/{location_id}")
        return location["path"]
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="list_locations",
    annotations={
        "title": "List Locations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_locations() -> str:
    """Return the full nested location hierarchy.

    The tree reflects physical storage tiers: cabinet > box > tray > slot (and
    album/page/pocket variants). Each node includes id, kind, label, and
    children.
    """
    try:
        result = await _client().request_json("GET", "/api/v1/locations/tree")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="add_location",
    annotations={
        "title": "Add Location",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def add_location(
    kind: str,
    label: str,
    parent_id: Optional[int] = None,
) -> str:
    """Create a new location node in the storage hierarchy.

    ``kind`` is the tier name: cabinet, box, tray, slot, album, page, or
    pocket. ``parent_id`` nests the new node under an existing location (omit
    for a top-level cabinet). Returns ``{id, path}`` for the new node.
    """
    try:
        body: dict[str, Any] = {"kind": kind, "label": label}
        if parent_id is not None:
            body["parent_id"] = parent_id
        result = await _client().request_json("POST", "/api/v1/locations", json=body)
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="list_sets",
    annotations={
        "title": "List Sets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_sets() -> str:
    """List set definitions with completion counts.

    Returns a JSON array; each entry includes filled/total slot counts for the
    set.
    """
    try:
        result = await _client().request_json("GET", "/api/v1/sets")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="set_gaps",
    annotations={
        "title": "Set Gaps",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_gaps(set_id: str) -> str:
    """List empty slots (missing date/mint combinations) for a set.

    ``set_id`` may be the numeric id or the set_key string. Returns
    ``{gaps: [...]}`` describing what is still needed to complete the set.
    """
    try:
        result = await _client().request_json("GET", f"/api/v1/sets/{set_id}/gaps")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="set_status",
    annotations={
        "title": "Set Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def set_status(set_id: str) -> str:
    """Get a set completion summary.

    ``set_id`` may be the numeric id or the set_key. Returns
    ``{filled, total, gaps}`` with counts and the list of missing slots.
    """
    try:
        result = await _client().request_json("GET", f"/api/v1/sets/{set_id}/status")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="portfolio_value",
    annotations={
        "title": "Portfolio Value",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def portfolio_value() -> str:
    """Get total portfolio value with melt and value-estimate breakdown by basis.

    All money values are integer cents (e.g. 500 = $5.00); responses also
    include ``*_display`` strings like ``"$5.00"`` for humans. This data is
    tool-sourced — never quote a portfolio figure you computed yourself; always
    call this tool and cite its output.
    """
    try:
        result = await _client().request_json("GET", "/api/v1/portfolio/value")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="melt_status",
    annotations={
        "title": "Melt Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def melt_status() -> str:
    """Read latest stored spot prices and portfolio melt values.

    All money values are integer cents (e.g. 500 = $5.00); responses also
    include ``*_display`` strings like ``"$5.00"`` for humans. Includes daily
    melt delta. PREFER THIS over ``melt_update`` for routine questions — it
    reads stored data with no external network calls.
    """
    try:
        result = await _client().request_json("GET", "/api/v1/melt/status")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="melt_update",
    annotations={
        "title": "Melt Update",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def melt_update() -> str:
    """Refresh melt values from live external spot-price sources.

    WARNING: This hits LIVE external spot-price sources (gold-api + Yahoo
    cross-check) and rewrites every coin melt value in the database. Run AT
    MOST once daily. For routine melt questions, prefer ``melt_status`` which
    reads stored data without network access.
    """
    try:
        result = await _client().request_json("POST", "/api/v1/melt/update")
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="record_appraisal",
    annotations={
        "title": "Record Appraisal",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def record_appraisal(
    accession: str,
    appraised_by: str,
    grade_bucket: Optional[str] = None,
    value_cents: Optional[int] = None,
    value_basis: Optional[str] = None,
    rationale: Optional[str] = None,
    token_cost: Optional[int] = None,
    confidence: Optional[float] = None,
) -> str:
    """Write an append-only appraisal record for a coin (never overwrites history).

    All money values are integer cents (e.g. 500 = $5.00); responses also
    include ``*_display`` strings like ``"$5.00"`` for humans. ``value_cents``
    and ``token_cost`` are INTEGER CENTS. A significant or asserted value change
    must be backed by one of these records before you state it to the user.

    Returns ``{appraisal_id, coin}`` with the new appraisal id and updated coin.
    """
    try:
        body = _body(
            appraised_by=appraised_by,
            grade_bucket=grade_bucket,
            value_cents=value_cents,
            value_basis=value_basis,
            rationale=rationale,
            token_cost=token_cost,
            confidence=confidence,
        )
        result = await _client().request_json(
            "POST",
            f"/api/v1/coins/{accession}/appraise",
            json=body,
        )
        return _dumps(result)
    except NumisLensError as exc:
        return f"Error: {exc}"


@mcp.tool(
    name="get_label_pdf",
    annotations={
        "title": "Get Label PDF",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_label_pdf(
    output_path: str,
    location_id: Optional[int] = None,
    accessions: Optional[list[str]] = None,
) -> str:
    """Generate a printable QR label sheet PDF and save it to a local path.

    Binary PDF data cannot travel through MCP directly, so the file is written
    to ``output_path`` on disk. Provide exactly one of ``location_id`` (all
    coins in that location subtree) or ``accessions`` (specific accession list).
    """
    if (location_id is None) == (accessions is None):
        return "Error: provide exactly one of location_id or accessions"
    try:
        if location_id is not None:
            params: dict[str, Any] = {"location_id": location_id}
        else:
            params = {"accessions": ",".join(accessions)}  # type: ignore[arg-type]
        resp = await _client().request("GET", "/api/v1/labels.pdf", params=params)
        Path(output_path).write_bytes(resp.content)
        return f"Saved label PDF to {output_path}"
    except NumisLensError as exc:
        return f"Error: {exc}"


if __name__ == "__main__":
    mcp.run()
