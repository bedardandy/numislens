"""Hand-rolled validation for set manifest JSON files."""

from __future__ import annotations

import json
from pathlib import Path

ALLOWED_MINTS = frozenset({"P", "D", "S", "O", "CC", "W"})

_TOP_LEVEL_KEYS = frozenset({"id", "name", "series", "composition_ref", "slots"})
_SLOT_KEYS = frozenset({"year", "mint", "key_date", "note"})


class ManifestError(ValueError):
    pass


def validate_manifest(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ManifestError(f"manifest must be a dict, got {type(data).__name__}")

    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            raise ManifestError(f"unknown top-level key: {key!r}")

    for field in ("id", "name", "composition_ref"):
        if field not in data:
            raise ManifestError(f"missing required field: {field!r}")
        value = data[field]
        if not isinstance(value, str):
            raise ManifestError(
                f"{field!r} must be a non-empty string, got {type(value).__name__}"
            )
        if not value:
            raise ManifestError(f"{field!r} must be a non-empty string")

    if "series" in data and not isinstance(data["series"], str):
        raise ManifestError(
            f"'series' must be a string, got {type(data['series']).__name__}"
        )

    if "slots" not in data:
        raise ManifestError("missing required field: 'slots'")
    slots = data["slots"]
    if not isinstance(slots, list):
        raise ManifestError(f"'slots' must be a list, got {type(slots).__name__}")
    if not slots:
        raise ManifestError("'slots' must be a non-empty list")

    seen: set[tuple[int, str, str]] = set()
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise ManifestError(
                f"slot {index} must be a dict, got {type(slot).__name__}"
            )

        for key in slot:
            if key not in _SLOT_KEYS:
                raise ManifestError(f"slot {index}: unknown key {key!r}")

        if "year" not in slot:
            raise ManifestError(f"slot {index}: missing required field 'year'")
        year = slot["year"]
        if not isinstance(year, int) or isinstance(year, bool):
            raise ManifestError(
                f"slot {index}: 'year' must be an integer, got {year!r}"
            )
        if year < 1600 or year > 2100:
            raise ManifestError(
                f"slot {index}: 'year' must be in range 1600..2100, got {year}"
            )

        if "mint" not in slot:
            raise ManifestError(f"slot {index}: missing required field 'mint'")
        mint = slot["mint"]
        if not isinstance(mint, str):
            raise ManifestError(
                f"slot {index}: 'mint' must be a string, got {type(mint).__name__}"
            )
        if mint not in ALLOWED_MINTS:
            raise ManifestError(
                f"slot {index}: invalid mint {mint!r}, allowed: {sorted(ALLOWED_MINTS)}"
            )

        if "key_date" in slot and not isinstance(slot["key_date"], bool):
            raise ManifestError(
                f"slot {index}: 'key_date' must be a boolean, got {type(slot['key_date']).__name__}"
            )

        if "note" in slot and not isinstance(slot["note"], str):
            raise ManifestError(
                f"slot {index}: 'note' must be a string, got {type(slot['note']).__name__}"
            )

        note = slot.get("note", "")
        identity = (year, mint, note)
        if identity in seen:
            raise ManifestError(
                f"slot {index}: duplicate slot (year={year}, mint={mint!r}, note={note!r})"
            )
        seen.add(identity)

    return data


def load_manifest(path: str | Path) -> dict:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {path}: {exc}") from exc

    return validate_manifest(data)
