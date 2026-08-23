"""Curated, source-cited coin value references (read-time estimates).

This is the honest answer to "what are my COMMON coins worth?" — the melt
engine only covers precious metal, and face value undersells every key date
sitting unnoticed in an inherited album. Datasets live in ``core/reference/
*.json`` next to ``reference.schema.json`` and carry MANDATORY provenance
(source name/URL/retrieved date). Every figure traces to a cited input.

Hard rules, in keeping with AGENTS.md invariant 1:

* Values are applied at READ time (the report), NEVER written to coins.
* Lookups require an EXACT match on series + year + mintmark + grade bucket.
  There is NO interpolation between grades, no fuzzy identity matching, no
  guessing. Unmatched means unresolved.
* Where multiple datasets cover one identity, the CONSERVATIVE (minimum)
  value wins for lookups; the ATTENTION (maximum) value drives worklist
  flagging — undervaluing is the safe error direction, but a flag should be
  loud enough to earn a look.
* Grade-null entries ("any condition") are FLAG-ONLY: they feed the appraisal
  worklist, never a stored or reported value.

Validation is hand-rolled like manifests.py: unknown keys raise, required
fields raise, values must be positive integer cents, graded ladders for one
identity must not descend as grade rises, and duplicate identities raise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Kept in lockstep with numislens_core.manifests.ALLOWED_MINTS and
# numislens_core.ledger.GRADE_BUCKETS. SYNC NOTE: update all three together.
ALLOWED_MINTS = frozenset({"P", "D", "S", "O", "CC", "W"})
GRADE_BUCKETS = frozenset({"AG", "G", "VG", "F", "VF", "XF", "AU", "UNC", "PROOF"})

_GRADE_RANK = {
    "AG": 0,
    "G": 1,
    "VG": 2,
    "F": 3,
    "VF": 4,
    "XF": 5,
    "AU": 6,
    "UNC": 7,
    # PROOF is a strike, not a rung of the wear ladder: excluded from the
    # monotonicity check because a proof can legitimately price below AU.
}

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "id",
    "name",
    "series",
    "country",
    "denomination",
    "notable_threshold_cents",
    "source",
    "entries",
})
_SOURCE_KEYS = frozenset({"name", "url", "retrieved", "notes"})
_ENTRY_KEYS = frozenset({"year", "mintmark", "grade", "value_cents", "note"})


class ReferenceError(ValueError):
    pass


def _require_str(where: str, data: dict, field: str) -> str:
    if field not in data:
        raise ReferenceError(f"{where}: missing required field {field!r}")
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        raise ReferenceError(f"{where}: {field!r} must be a non-empty string")
    return value


def _validate_source(where: str, source) -> None:
    if not isinstance(source, dict):
        raise ReferenceError(
            f"{where}: 'source' must be an object with name/url/retrieved"
        )
    for key in source:
        if key not in _SOURCE_KEYS:
            raise ReferenceError(f"{where}: unknown source key {key!r}")
    for field in ("name", "url", "retrieved"):
        if field not in source:
            raise ReferenceError(f"{where}: source missing required field {field!r}")
        if not isinstance(source[field], str) or not source[field].strip():
            raise ReferenceError(f"{where}: source.{field} must be a non-empty string")
    url = source["url"]
    if not url.startswith(("http://", "https://")):
        raise ReferenceError(f"{where}: source.url must be an http(s) URL: {url!r}")
    if not _DATE_RE.match(source["retrieved"]):
        raise ReferenceError(
            f"{where}: source.retrieved must be YYYY-MM-DD, got {source['retrieved']!r}"
        )


def validate_reference(data: dict) -> dict:
    """Validate one reference dataset; returns it unchanged. Fails loud."""
    if not isinstance(data, dict):
        raise ReferenceError(f"reference must be a dict, got {type(data).__name__}")

    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            raise ReferenceError(f"unknown top-level key: {key!r}")

    version = data.get("schema_version")
    if version != 1:
        raise ReferenceError(
            f"'schema_version' must be 1, got {version!r}"
        )

    _require_str("reference", data, "id")
    _require_str("reference", data, "name")

    series = _require_str("reference", data, "series")

    country = data.get("country", "US")
    if country != "US":
        # FACE_CENTS and the whole quick-add vocabulary are US-scoped today;
        # a non-US dataset would silently misreport. Extend deliberately.
        raise ReferenceError(f"only country='US' datasets are supported, got {country!r}")

    if "denomination" in data and not isinstance(data["denomination"], str):
        raise ReferenceError("'denomination' must be a string")

    threshold = data.get("notable_threshold_cents", 100)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
        raise ReferenceError(
            "'notable_threshold_cents' must be a positive integer (cents)"
        )

    _validate_source("reference", data.get("source"))

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ReferenceError("'entries' must be a non-empty list")

    seen_identities: set[tuple[int, str | None, str | None]] = set()
    ladder: dict[tuple[int, str | None], list[tuple[int, int]]] = {}
    for index, entry in enumerate(entries):
        where = f"{series} entry {index}"
        if not isinstance(entry, dict):
            raise ReferenceError(f"{where}: must be a dict")
        for key in entry:
            if key not in _ENTRY_KEYS:
                raise ReferenceError(f"{where}: unknown key {key!r}")

        if "year" not in entry:
            raise ReferenceError(f"{where}: missing required field 'year'")
        year = entry["year"]
        if (
            not isinstance(year, int)
            or isinstance(year, bool)
            or year < 1600
            or year > 2100
        ):
            raise ReferenceError(f"{where}: 'year' must be an integer 1600..2100")

        mintmark = entry.get("mintmark")
        if mintmark is not None and (
            not isinstance(mintmark, str) or mintmark not in ALLOWED_MINTS
        ):
            raise ReferenceError(
                f"{where}: mintmark must be null or one of {sorted(ALLOWED_MINTS)}"
            )

        grade = entry.get("grade")
        if grade is not None and (
            not isinstance(grade, str) or grade not in GRADE_BUCKETS
        ):
            raise ReferenceError(
                f"{where}: grade must be null or one of {sorted(GRADE_BUCKETS)}"
            )

        if "value_cents" not in entry:
            raise ReferenceError(f"{where}: missing required field 'value_cents'")
        value = entry["value_cents"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ReferenceError(
                f"{where}: value_cents must be a positive integer, got {value!r}"
            )
        if "note" in entry and not isinstance(entry["note"], str):
            raise ReferenceError(f"{where}: note must be a string")

        identity = (year, mintmark, grade)
        if identity in seen_identities:
            raise ReferenceError(f"{where}: duplicate identity {identity}")
        seen_identities.add(identity)

        if grade in _GRADE_RANK:
            ladder.setdefault((year, mintmark), []).append((_GRADE_RANK[grade], value))

    # A graded ladder must not descend as grade rises — this catches transposed
    # rows, the classic typo in hand-curated tables.
    for (year, mintmark), rungs in ladder.items():
        rungs.sort()
        for (_, lower_value), (_, higher_value) in zip(rungs, rungs[1:]):
            if higher_value < lower_value:
                raise ReferenceError(
                    f"{series} {year}{mintmark or ''}: graded values must not "
                    f"descend as grade rises ({lower_value} -> {higher_value})"
                )

    return data


def load_reference(path: str | Path) -> dict:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReferenceError(f"cannot read reference {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReferenceError(f"invalid JSON in {path}: {exc}") from exc
    return validate_reference(data)


class ReferenceSet:
    """All loaded datasets with conservative lookup + attention flagging."""

    def __init__(self, datasets: list[dict]) -> None:
        self.datasets = datasets

    def __len__(self) -> int:
        return len(self.datasets)

    def sources(self) -> list[dict]:
        """Provenance of every dataset that contributed, for report output."""
        return [
            {
                "id": d["id"],
                "name": d["name"],
                "series": d["series"],
                "source": d["source"],
            }
            for d in self.datasets
        ]

    def _matching_datasets(self, series: str):
        series_lower = series.lower()
        for d in self.datasets:
            if d["series"].lower() == series_lower:
                yield d

    @staticmethod
    def _mintmark_matches(entry_mintmark, coin_mintmark) -> bool:
        if entry_mintmark is None:
            return True  # wildcard: matches any mintmark, including none
        return coin_mintmark == entry_mintmark

    def lookup(self, series: str, year: int, mintmark, grade_bucket) -> int | None:
        """Exact-match value lookup; MIN across datasets (conservative).

        Requires a known series, exact year, wildcard-or-exact mintmark, and
        an EXACT graded entry. Grade-null entries never produce values. Any
        miss returns None — unresolved, never interpolated.
        """
        if not series or year is None or grade_bucket is None:
            return None
        best: int | None = None
        for d in self._matching_datasets(series):
            for entry in d["entries"]:
                if entry["grade"] is None:
                    continue
                if entry["year"] != year:
                    continue
                if not self._mintmark_matches(entry["mintmark"], mintmark):
                    continue
                if entry["grade"] != grade_bucket:
                    continue
                value = entry["value_cents"]
                if best is None or value < best:
                    best = value
        return best

    def notable_value(self, series: str, year: int, mintmark) -> int | None:
        """Attention value for a coin's IDENTITY, ignoring grade (or None).

        The MAX value among entries at or above the dataset's notable
        threshold whose identity matches (wildcard mintmarks included).
        This is worklist fuel only — never written anywhere.
        """
        if not series or year is None:
            return None
        best: int | None = None
        for d in self._matching_datasets(series):
            threshold = d.get("notable_threshold_cents", 100)
            for entry in d["entries"]:
                if entry["value_cents"] < threshold:
                    continue
                if entry["year"] != year:
                    continue
                if not self._mintmark_matches(entry["mintmark"], mintmark):
                    continue
                value = entry["value_cents"]
                if best is None or value > best:
                    best = value
        return best


def load_references(directory: str | Path | None = None) -> ReferenceSet:
    """Load + validate every dataset in ``core/reference/*.json``.

    Unlike albums.load_manifests (which skips broken files), a broken shipped
    dataset FAILS LOUD here: silently losing valuation coverage is its own
    quiet-fabrication failure mode. Schema files (*.schema.json) are skipped.
    """
    directory = Path(directory) if directory else REFERENCE_DIR
    datasets: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".schema.json"):
            continue
        datasets.append(load_reference(path))
    return ReferenceSet(datasets)
