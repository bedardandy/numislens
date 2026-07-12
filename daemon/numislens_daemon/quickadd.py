"""Deterministic free-text parser for the quick-add endpoint.

This is the anti-confabulation core of NumisLens quick capture. It parses short
dictated/typed phrases like::

    "1943 steel cent, box 3 slot 12, paid $4"
    "add 1885 Morgan dollar CC to tray 2"

into ledger fields using ONLY regex and lookup tables — NO LLM, NO network, NO
guessing. Every rule below is either a fact literally stated in the text (a year
token, a denomination word, a "$" amount) or a numismatically CERTAIN
consequence of such a fact. Anything it cannot map cleanly is returned in
``unresolved`` rather than fabricated, and any input text the parser could not
consume is echoed back as ``unrecognized: "..."`` entries so nothing is silently
dropped. Grade is never parsed or set.

The LLM enrichment tier described in the direction doc (Gemma micro-call) is a
LATER phase; this module deliberately layers underneath it.
"""

from __future__ import annotations

import re
from typing import Any

Span = tuple[int, int]

# --- Mintmarks -------------------------------------------------------------
# The U.S. mintmark alphabet we accept. A single letter/pair only counts as a
# mintmark when it is ADJACENT to a year ("1885-CC", "1885 CC") or to a matched
# series phrase ("Morgan dollar CC"). A bare "CC" floating in the text is NOT a
# mintmark (it could be anything); it is reported back as unrecognized text.
_MINTMARKS = {"P", "D", "S", "O", "CC", "W"}
_MINT_LOWER = {m.lower() for m in _MINTMARKS}

# --- Series aliases --------------------------------------------------------
# Maps SPECIFIC, unambiguous shorthand to a canonical series name. Generic
# denomination words (cent, nickel, dime, quarter, half dollar, dollar) are
# deliberately NOT here: a bare "quarter" could be Washington, Standing Liberty,
# Barber, etc., so mapping it to a series would be fabrication. Those words set
# the `denomination` field only (see _DENOMINATIONS). The distinct series names
# from the loaded set manifests are merged with these at parse time.
_SERIES_ALIASES = {
    "morgan dollar": "Morgan Dollar",
    "morgan": "Morgan Dollar",
    "peace dollar": "Peace Dollar",
    "peace": "Peace Dollar",
    "washington quarter": "Washington Quarter",
    "lincoln wheat cent": "Lincoln Wheat Cent",
    "wheat cent": "Lincoln Wheat Cent",
    "wheat penny": "Lincoln Wheat Cent",
    "steel cent": "Lincoln Wheat Cent",
    "steel penny": "Lincoln Wheat Cent",
    "lincoln cent": "Lincoln Cent",
    "lincoln penny": "Lincoln Cent",
}

# --- Denomination words ----------------------------------------------------
# (phrase, canonical denomination). Longest phrases first so "half dollar" wins
# over "dollar". These state the denomination literally; they never imply series.
_DENOMINATIONS: list[tuple[str, str]] = [
    ("half dollar", "half dollar"),
    ("half", "half dollar"),
    ("dollar", "dollar"),
    ("quarter", "quarter"),
    ("dime", "dime"),
    ("nickel", "nickel"),
    ("cent", "cent"),
    ("penny", "cent"),
]

# Canonical denomination implied by a resolved series (a stated fact once the
# series is known).
_SERIES_DENOMINATION = {
    "Morgan Dollar": "dollar",
    "Peace Dollar": "dollar",
    "Washington Quarter": "quarter",
    "Lincoln Wheat Cent": "cent",
    "Lincoln Cent": "cent",
}

# --- Location kind vocabulary ---------------------------------------------
# Words that introduce a "<kind> <label>" location token, e.g. "box 3",
# "tray 2", "slot 12". Only used to READ a location phrase; locations are
# resolved against EXISTING labels and are NEVER auto-created.
_LOCATION_KINDS = {
    "cabinet", "box", "tray", "slot", "album", "page", "row", "pocket",
    "drawer", "folder", "binder", "tube", "case", "shelf", "bin", "sleeve",
}

# --- Filler words ----------------------------------------------------------
# Connective tissue that carries no coin fact. Stripped from residual segments
# before they are reported as unrecognized (so "bought 1999" reports "1999",
# not the verb). Keep this list conservative: when in doubt, report the word.
_FILLER_WORDS = {
    "a", "an", "the", "and", "add", "added", "to", "in", "into", "on", "at",
    "of", "for", "my", "it", "is", "this", "that", "just", "please", "put",
    "with", "from", "i", "coin", "coins", "paid", "bought", "cost", "get",
    "got", "new",
}

_YEAR_WORD_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
_YEAR_MINT_RE = re.compile(r"\b(1[5-9]\d\d|20\d\d)-([a-z]{1,2})\b")
# "$4", "$1,234.56", or "paid/cost 4.50". The paid/cost-keyword branch is tried
# first so the span covers the whole "paid $4" phrase; a bare "$" amount is
# still matched on its own.
_MONEY_RE = re.compile(
    r"(?:\b(?:paid|cost)\s+\$?\s*(?P<kw>\d[\d,]*(?:\.\d{1,2})?))"
    r"|(?:\$\s*(?P<dollar>\d[\d,]*(?:\.\d{1,2})?))"
)


def _money_to_cents(raw: str) -> int:
    """Port of public/js/money.js dollarsToCents, integer cents, no floats."""
    amount = raw.strip().lstrip("$").replace(",", "")
    m = re.fullmatch(r"(\d*)(?:\.(\d{1,2}))?", amount)
    if not m or (m.group(1) == "" and not m.group(2)):
        raise ValueError(f"invalid dollar amount: {raw!r}")
    dollars_part = m.group(1) or "0"
    cents_part = (m.group(2) or "").ljust(2, "0")
    return int(dollars_part) * 100 + int(cents_part)


def _extract_money(text: str) -> tuple[int | None, str | None, Span | None]:
    """Return (cents, unresolved_fragment, span). The span is masked before
    year parsing so a "$1943" price is never mistaken for a year."""
    m = _MONEY_RE.search(text)
    if m is None:
        return None, None, None
    raw = m.group("kw") if m.group("kw") is not None else m.group("dollar")
    try:
        return _money_to_cents(raw), None, m.span()
    except ValueError:
        return None, m.group(0).strip(), m.span()


def _match_series(
    lowered: str, series_names: list[str]
) -> tuple[str | None, str | None, Span | None]:
    """Return (canonical_series, matched_phrase, span). Longest phrase wins."""
    candidates: dict[str, str] = {}
    for name in series_names:
        if name:
            candidates[name.lower()] = name
    # Alias table can override / extend, mapping shorthand -> canonical.
    for phrase, canonical in _SERIES_ALIASES.items():
        candidates.setdefault(phrase, canonical)
    for phrase in sorted(candidates, key=len, reverse=True):
        m = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
        if m is not None:
            return candidates[phrase], phrase, m.span()
    return None, None, None


def _match_denomination(lowered: str) -> tuple[str | None, Span | None]:
    for phrase, canonical in _DENOMINATIONS:
        m = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
        if m is not None:
            return canonical, m.span()
    return None, None


def _extract_year_and_mint(
    text_lower: str, series_phrase: str | None
) -> tuple[int | None, str | None, list[Span]]:
    """Return (year, mintmark, consumed_spans).

    Only the FIRST year candidate becomes the year; any later year tokens are
    left unconsumed so the residual pass reports them as unrecognized (never
    silently dropped).
    """
    year: int | None = None
    mintmark: str | None = None
    spans: list[Span] = []

    # 1. Combined "1885-CC" token.
    ym = _YEAR_MINT_RE.search(text_lower)
    if ym is not None and ym.group(2) in _MINT_LOWER:
        year = int(ym.group(1))
        mintmark = ym.group(2).upper()
        spans.append(ym.span())
    else:
        yw = _YEAR_WORD_RE.search(text_lower)
        if yw is not None:
            year = int(yw.group(1))
            spans.append(yw.span())
            # 2. "1885 CC" — mint token immediately after the year token.
            tokens = [
                (t.group(0), t.span())
                for t in re.finditer(r"[a-z]+|\d{3,4}", text_lower)
            ]
            for i, (_tok, sp) in enumerate(tokens):
                if sp == yw.span():
                    if i + 1 < len(tokens) and tokens[i + 1][0] in _MINT_LOWER:
                        mintmark = tokens[i + 1][0].upper()
                        spans.append(tokens[i + 1][1])
                    break

    # 3. "Morgan dollar CC" — mint token immediately after the series phrase.
    if mintmark is None and series_phrase is not None:
        m = re.search(
            re.escape(series_phrase) + r"\s+([a-z]{1,2})\b", text_lower
        )
        if m is not None and m.group(1) in _MINT_LOWER:
            mintmark = m.group(1).upper()
            spans.append(m.span(1))

    return year, mintmark, spans


def _certain_composition(
    series: str | None, year: int | None, has_steel_kw: bool
) -> tuple[str | None, bool]:
    """Return (composition_name, uncertain).

    Only numismatically CERTAIN rules fire. ``uncertain`` is True when a
    composition is plausible but not certain, so the caller lists it in
    ``unresolved`` instead of guessing.

    - steel cent: the word "steel" names the metal, but the only regular-issue
      steel cent is 1943 — so the rule fires only when the year is absent or
      exactly 1943. Any other stated year (e.g. "1957 steel cent") is an
      impossible combination — the user likely misspoke — so composition stays
      null and is listed unresolved. (1944 steel-planchet errors are collector
      exotica and deliberately NOT encoded.)
    - Morgan dollar 1878-1921 -> 90% silver dollar (.900 fine for the whole
      classic run). Peace dollar 1921-1935 likewise. Modern (2021+) Morgan/Peace
      commemoratives are .999 fine, so the year gate is REQUIRED for certainty.
    """
    if has_steel_kw:
        if year is None or year == 1943:
            return "Steel cent", False
        return None, True
    if series == "Morgan Dollar":
        if year is not None and 1878 <= year <= 1921:
            return "90% silver dollar", False
        return None, True
    if series == "Peace Dollar":
        if year is not None and 1921 <= year <= 1935:
            return "90% silver dollar", False
        return None, True
    return None, False


def _parse_location_pairs(lowered: str) -> list[tuple[str, str, Span]]:
    pairs: list[tuple[str, str, Span]] = []
    for m in re.finditer(r"\b([a-z]+)\s+([a-z0-9][a-z0-9-]*)\b", lowered):
        if m.group(1) in _LOCATION_KINDS:
            pairs.append((m.group(1), m.group(2), m.span()))
    return pairs


def _resolve_location(
    pairs: list[tuple[str, str]], locations: list[dict]
) -> tuple[int | None, str | None]:
    """Resolve a location phrase against EXISTING locations.

    A location matches token ``(kind, value)`` when its kind matches (case-
    insensitively) and its label equals ``value`` or ``"<kind> <value>"``. The
    deepest token must match, and every shallower token must match some ancestor.
    Returns ``(location_id, None)`` only on a UNIQUE match; otherwise
    ``(None, phrase)`` so the caller lists it unresolved. Never auto-creates.
    """
    if not pairs:
        return None, None
    by_id = {loc["id"]: loc for loc in locations}

    def matches(loc: dict, kind_t: str, val_t: str) -> bool:
        if str(loc["kind"]).lower() != kind_t:
            return False
        label = str(loc["label"]).lower()
        return label == val_t or label == f"{kind_t} {val_t}"

    def ancestry(loc: dict) -> list[dict]:
        chain: list[dict] = []
        seen: set[int] = set()
        cur: dict | None = loc
        while cur is not None and cur["id"] not in seen:
            seen.add(cur["id"])
            chain.append(cur)
            parent_id = cur["parent_id"]
            cur = by_id.get(parent_id) if parent_id is not None else None
        return chain

    deep_kind, deep_val = pairs[-1]
    candidates = [loc for loc in locations if matches(loc, deep_kind, deep_val)]
    good: list[dict] = []
    for cand in candidates:
        chain = ancestry(cand)
        if all(
            any(matches(a, kind_t, val_t) for a in chain)
            for kind_t, val_t in pairs[:-1]
        ):
            good.append(cand)

    phrase = " ".join(f"{k} {v}" for k, v in pairs)
    if len(good) == 1:
        return good[0]["id"], None
    return None, phrase


_MASK_CHAR = "\x00"
_PUNCTUATION = set(",.;:!?()[]{}'\"-")


def _residual_unrecognized(lowered: str, spans: list[Span]) -> list[str]:
    """Report input text no extractor consumed, as ``unrecognized: "..."``.

    Consumed spans are masked out; punctuation becomes whitespace; what remains
    is grouped into contiguous segments (a masked region splits segments so
    unrelated leftovers are reported separately). Filler words are stripped and
    a segment that was pure filler is dropped. This enforces the tell-the-user
    contract: nothing typed is ever silently ignored.
    """
    chars = list(lowered)
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            chars[i] = _MASK_CHAR
    for i, ch in enumerate(chars):
        if ch in _PUNCTUATION:
            chars[i] = " "
    masked = "".join(chars)

    segments: list[list[str]] = []
    current: list[str] = []
    prev_end: int | None = None
    for m in re.finditer(rf"[^\s{_MASK_CHAR}]+", masked):
        if prev_end is not None and _MASK_CHAR in masked[prev_end : m.start()]:
            if current:
                segments.append(current)
            current = []
        current.append(m.group(0))
        prev_end = m.end()
    if current:
        segments.append(current)

    out: list[str] = []
    for segment in segments:
        kept = [tok for tok in segment if tok not in _FILLER_WORDS]
        if kept:
            out.append('unrecognized: "%s"' % " ".join(kept))
    return out


def parse_quick_add(
    text: str,
    *,
    compositions: list[dict],
    series_names: list[str],
    locations: list[dict],
) -> dict[str, Any]:
    """Parse free text into ``{"parsed": {...}, "unresolved": [...]}``.

    Pure function (no DB/network). ``parsed`` holds only fields that resolved
    cleanly; ``unresolved`` lists phrases/tokens that were recognized as
    meaningful but could not be mapped without guessing, PLUS an
    ``unrecognized: "..."`` entry for any leftover text no extractor consumed.
    The caller decides whether to create a coin (needs at least a series or a
    year).
    """
    if not isinstance(text, str) or not text.strip():
        return {"parsed": {}, "unresolved": ["empty input"]}

    lowered = text.lower()
    parsed: dict[str, Any] = {}
    unresolved: list[str] = []
    consumed: list[Span] = []

    # Money first, then mask its span so a "$1943" is not read as a year.
    cents, money_unresolved, money_span = _extract_money(lowered)
    if cents is not None:
        parsed["cost_basis_cents"] = cents
    if money_unresolved is not None:
        unresolved.append(money_unresolved)
    year_source = lowered
    if money_span is not None:
        consumed.append(money_span)
        start, end = money_span
        year_source = lowered[:start] + " " * (end - start) + lowered[end:]

    # Series (also merges distinct manifest series names).
    series, series_phrase, series_span = _match_series(lowered, series_names)
    if series is not None:
        parsed["series"] = series
    if series_span is not None:
        consumed.append(series_span)

    # Year + mintmark (adjacency-gated). Only the FIRST year candidate is used;
    # later year tokens fall through to the residual pass as unrecognized.
    year, mintmark, ym_spans = _extract_year_and_mint(year_source, series_phrase)
    if year is not None:
        parsed["year"] = year
    if mintmark is not None:
        parsed["mintmark"] = mintmark
    consumed.extend(ym_spans)

    # Denomination: series wins; else a bare denomination word (stated fact).
    # The word's span is consumed either way so a denomination word inside or
    # alongside a series phrase is not re-reported as unrecognized.
    denom, denom_span = _match_denomination(lowered)
    if series is not None and series in _SERIES_DENOMINATION:
        parsed["denomination"] = _SERIES_DENOMINATION[series]
    elif denom is not None:
        parsed["denomination"] = denom
    if denom_span is not None:
        consumed.append(denom_span)

    # Certain composition only.
    has_steel_kw = bool(re.search(r"\bsteel\s+(?:cent|penny)\b", lowered))
    comp_name, comp_uncertain = _certain_composition(series, year, has_steel_kw)
    if comp_name is not None:
        comp = next(
            (
                c
                for c in compositions
                if str(c.get("name", "")).lower() == comp_name.lower()
            ),
            None,
        )
        if comp is not None:
            parsed["composition_id"] = comp["id"]
            # value_basis default per composition: a precious-metal composition
            # gets a melt FLOOR (hybrid) — never a fabricated numismatic value.
            # Base metal (steel cent) leaves value_basis null.
            if comp.get("metal") is not None and comp.get("precious_weight_ozt") is not None:
                parsed["value_basis"] = "hybrid"
        else:
            unresolved.append("composition")
    elif comp_uncertain:
        unresolved.append("composition")

    # Location: resolve against existing labels only. The phrase's span is
    # consumed whether or not it resolves (an unresolved phrase is already
    # reported verbatim; do not double-report it as unrecognized).
    triples = _parse_location_pairs(lowered)
    consumed.extend(sp for _, _, sp in triples)
    loc_id, loc_unresolved = _resolve_location(
        [(k, v) for k, v, _ in triples], locations
    )
    if loc_id is not None:
        parsed["location_id"] = loc_id
    if loc_unresolved is not None:
        unresolved.append(loc_unresolved)

    # Tell-the-user contract: whatever no extractor consumed is echoed back.
    unresolved.extend(_residual_unrecognized(lowered, consumed))

    return {"parsed": parsed, "unresolved": unresolved}
