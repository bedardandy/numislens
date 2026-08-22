"""CSV export/import for the coin ledger — round-trippable, integer cents.

The CSV is the portability contract: stable column order, money as raw
integer-cent strings (never floats or "$" display forms), composition
referenced by NAME and location by PATH (database-local IDs do not survive a
round-trip across databases). ``accession_no`` is exported for provenance but
IGNORED on import — accessions are server-assigned.

Import is strict and ALL-OR-NOTHING: every row is validated before anything
is created; any problem aborts the whole import with every row error listed.
This mirrors the watch/digest pre-validation pattern and the fail-loud rule —
a half-imported collection is exactly the silent-corruption failure mode this
platform exists to avoid.
"""

from __future__ import annotations

import csv
import io

# Stable export/import column order. Money columns carry integer cents.
COIN_CSV_COLUMNS: tuple[str, ...] = (
    "accession_no",
    "series",
    "year",
    "mintmark",
    "denomination",
    "country",
    "grade_bucket",
    "tpg_cert",
    "composition",
    "cost_basis_cents",
    "acquired_date",
    "acquired_source",
    "value_est_cents",
    "value_basis",
    "appraisal_confidence",
    "location",
    "notes",
    "disposition",
    "sold_date",
    "sold_price_cents",
    "sold_venue",
)

_CENTS_FIELDS = ("cost_basis_cents", "value_est_cents", "sold_price_cents")
_ENUMS = {
    "grade_bucket": frozenset({"AG", "G", "VG", "F", "VF", "XF", "AU", "UNC", "PROOF"}),
    "value_basis": frozenset({"melt", "numismatic", "hybrid"}),
    "disposition": frozenset({"owned", "for_sale", "sold", "discarded"}),
}


class CsvImportError(ValueError):
    """Raised when an import CSV fails validation. Carries per-row errors."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            f"import rejected: {len(errors)} problem(s); nothing was created"
        )


def coin_to_csv_row(
    coin: dict,
    *,
    composition_name: str | None = None,
    location_path: str | None = None,
) -> dict[str, str]:
    """Shape one coin DB row into CSV cells (None -> empty string)."""

    def cell(value) -> str:
        return "" if value is None else str(value)

    return {
        "accession_no": cell(coin.get("accession_no")),
        "series": cell(coin.get("series")),
        "year": cell(coin.get("year")),
        "mintmark": cell(coin.get("mintmark")),
        "denomination": cell(coin.get("denomination")),
        "country": cell(coin.get("country")),
        "grade_bucket": cell(coin.get("grade_bucket")),
        "tpg_cert": cell(coin.get("tpg_cert")),
        "composition": cell(composition_name),
        "cost_basis_cents": cell(coin.get("cost_basis_cents")),
        "acquired_date": cell(coin.get("acquired_date")),
        "acquired_source": cell(coin.get("acquired_source")),
        "value_est_cents": cell(coin.get("value_est_cents")),
        "value_basis": cell(coin.get("value_basis")),
        "appraisal_confidence": cell(coin.get("appraisal_confidence")),
        "location": cell(location_path),
        "notes": cell(coin.get("notes")),
        "disposition": cell(coin.get("disposition")),
        "sold_date": cell(coin.get("sold_date")),
        "sold_price_cents": cell(coin.get("sold_price_cents")),
        "sold_venue": cell(coin.get("sold_venue")),
    }


def coins_to_csv(rows: list[dict[str, str]]) -> str:
    """Serialize already-shaped rows (see :func:`coin_to_csv_row`) to text."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(COIN_CSV_COLUMNS))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _cell_or_none(raw: str) -> str | None:
    raw = raw.strip()
    return raw if raw else None


def parse_coins_csv(
    text: str,
    *,
    composition_ids_by_name: dict[str, int],
    location_ids_by_path: dict[str, int],
) -> list[dict]:
    """Parse + fully validate an import CSV into add_coin kwargs.

    Raises :class:`CsvImportError` carrying one message per bad row if ANY row
    is invalid — nothing is created by the caller in that case.

    ``composition_ids_by_name`` maps lowercase composition names to ids;
    ``location_ids_by_path`` maps lowercase 'cabinet > box 1' style paths to
    ids. Unknown names/paths are row errors (locations are never auto-created).
    """
    errors: list[str] = []
    parsed: list[dict] = []

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    # Any export column is a legal import header; accession_no values are
    # simply ignored (server-assigned). Anything else is rejected loudly.
    unknown_cols = [c for c in header if c not in COIN_CSV_COLUMNS]
    if unknown_cols:
        raise CsvImportError([
            "unknown column(s): "
            + ", ".join(sorted(unknown_cols))
            + f" (allowed: {', '.join(sorted(COIN_CSV_COLUMNS))})"
        ])
    if not any(c in header for c in ("series", "year")):
        # Rows will fail individually below; add one clear cause up front too.
        errors.append(
            "header has neither a 'series' nor a 'year' column — "
            "no row could identify a coin"
        )

    for line_no, row in enumerate(reader, start=2):
        label = f"row {line_no}"
        # DictReader stows surplus cells under a None key (ragged row); ignore
        # them rather than crash — column validation above already pins shape.
        cells = {
            k: (_cell_or_none(v) if v is not None else None)
            for k, v in row.items()
            if k is not None
        }
        series = cells.get("series")
        year_raw = cells.get("year")
        if series is None and year_raw is None:
            errors.append(f"{label}: need at least a series or a year")
            continue

        fields: dict = {}
        for col in (
            "series", "mintmark", "denomination", "country", "tpg_cert",
            "acquired_date", "acquired_source", "notes", "sold_date",
            "sold_venue",
        ):
            if cells.get(col) is not None:
                fields[col] = cells[col]
        if year_raw is not None:
            try:
                fields["year"] = int(year_raw)
            except ValueError:
                errors.append(f"{label}: year must be an integer, got {year_raw!r}")
                continue

        bad_enum = False
        for col, allowed in _ENUMS.items():
            value = cells.get(col)
            if value is None:
                continue
            if col == "grade_bucket":
                value = value.upper()
            if value not in allowed:
                errors.append(f"{label}: invalid {col}: {value!r}")
                bad_enum = True
        if bad_enum:
            continue
        if "grade_bucket" in cells and cells["grade_bucket"] is not None:
            fields["grade_bucket"] = cells["grade_bucket"].upper()
        for col in ("value_basis", "disposition"):
            if cells.get(col) is not None:
                fields[col] = cells[col]

        bad_money = False
        for col in _CENTS_FIELDS:
            value = cells.get(col)
            if value is None:
                continue
            if not value.isdigit():
                errors.append(
                    f"{label}: {col} must be non-negative integer cents, got {value!r}"
                )
                bad_money = True
                continue
            fields[col] = int(value)
        if bad_money:
            continue

        confidence_raw = cells.get("appraisal_confidence")
        if confidence_raw is not None:
            try:
                fields["appraisal_confidence"] = float(confidence_raw)
            except ValueError:
                errors.append(
                    f"{label}: appraisal_confidence must be a number, got {confidence_raw!r}"
                )
                continue

        comp_name = cells.get("composition")
        if comp_name is not None:
            comp_id = composition_ids_by_name.get(comp_name.lower())
            if comp_id is None:
                errors.append(f"{label}: unknown composition: {comp_name!r}")
                continue
            fields["composition_id"] = comp_id

        loc_path = cells.get("location")
        if loc_path is not None:
            loc_id = location_ids_by_path.get(loc_path.lower())
            if loc_id is None:
                errors.append(
                    f"{label}: unknown location path: {loc_path!r} "
                    "(create locations first; they are never auto-created)"
                )
                continue
            fields["location_id"] = loc_id

        if fields.get("disposition") == "sold" and "sold_price_cents" not in fields:
            errors.append(
                f"{label}: disposition='sold' requires sold_price_cents "
                "(use 0 for a giveaway)"
            )
            continue

        parsed.append(fields)

    if errors:
        raise CsvImportError(errors)
    return parsed
