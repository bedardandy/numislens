"""Exact dollar-string -> integer-cents parsing (no floats).

Single source of truth for the "$4" / "1,234.56" grammar used by the CLI
(`--cost`/`--value`) and the daemon's quick-add parser. A port of
public/js/money.js dollarsToCents: integer cents everywhere, never a float —
invariant 4 in AGENTS.md.
"""

from __future__ import annotations

import re

_DOLLARS_RE = re.compile(r"(\d*)(?:\.(\d{1,2}))?")


def parse_dollars_to_cents(raw: str) -> int:
    """Parse a dollar amount string into exact integer cents.

    Accepts an optional leading ``$``, thousands commas, and 0-2 decimal
    places ("$4", "19.99", "1,234.5"). Raises ValueError on anything else —
    including negative and bare-decimal-only inputs — rather than guessing.
    """
    if not isinstance(raw, str):
        raise ValueError(f"invalid dollar amount: {raw!r}")
    amount = raw.strip().lstrip("$").replace(",", "")
    m = _DOLLARS_RE.fullmatch(amount)
    if not m or (m.group(1) == "" and not m.group(2)):
        raise ValueError(f"invalid dollar amount: {raw!r}")
    dollars_part = m.group(1) or "0"
    cents_part = (m.group(2) or "").ljust(2, "0")
    return int(dollars_part) * 100 + int(cents_part)
