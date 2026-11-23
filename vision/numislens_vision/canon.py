"""Deterministic boundary canonicalization for model outputs.

This is the anti-confabulation seam of the vision pipeline. Vision models
(Qwen especially) paraphrase enum tokens, rename JSON keys, and autocomplete
identity-critical text. NOTHING a model returns is trusted as-is: every value
crosses one of the functions here, which map free text to a CANONICAL token
from a fixed allowed set, or return ``None`` (unresolved) — never a guess.

Mirrors the enum/alias discipline in ``daemon/numislens_daemon/quickadd.py``.
"""

from __future__ import annotations

import json
import re

# Kept in lockstep with numislens_core.ledger.GRADE_BUCKETS and the direction
# doc's photograde ladder. PROOF is intentionally NOT reachable from wear
# descriptions (proof is a strike, not a grade a phone photo infers).
GRADE_BUCKETS = ("AG", "G", "VG", "F", "VF", "XF", "AU", "UNC")

# Mintmark alphabet — identical to numislens_core.manifests.ALLOWED_MINTS and
# quickadd._MINTMARKS. "NONE" is a sentinel meaning the reader affirmatively
# saw NO mintmark (distinct from "couldn't tell" == None).
MINTMARKS = ("CC", "P", "D", "S", "O", "W")  # CC first: two-letter, match before D/C
MINT_NONE = "NONE"

# --- Series aliases --------------------------------------------------------
# DUPLICATED (small, stable) from quickadd._SERIES_ALIASES. SYNC NOTE: if you
# add a series alias in daemon/numislens_daemon/quickadd.py, add it here too.
# The pipeline also merges canonical series names fetched live from the daemon
# (loaded sets), so this table only needs the shorthand the VLM tends to emit.
_SERIES_ALIASES = {
    "morgan dollar": "Morgan Dollar",
    "morgan": "Morgan Dollar",
    "peace dollar": "Peace Dollar",
    "peace": "Peace Dollar",
    "washington quarter": "Washington Quarter",
    "lincoln wheat cent": "Lincoln Wheat Cent",
    "lincoln wheat penny": "Lincoln Wheat Cent",
    "wheat cent": "Lincoln Wheat Cent",
    "wheat penny": "Lincoln Wheat Cent",
    "steel cent": "Lincoln Wheat Cent",
    "steel penny": "Lincoln Wheat Cent",
    "lincoln cent": "Lincoln Cent",
    "lincoln penny": "Lincoln Cent",
    "lincoln memorial cent": "Lincoln Cent",
}

# --- Grade synonyms --------------------------------------------------------
# Longest phrases first so "very fine" wins over "fine", "about uncirculated"
# over "uncirculated", etc. Numeric grades (MS-63, AU-58, "grade 63") are
# deliberately collapsed to their BUCKET: the whole point of the honesty rule is
# that a phone photo yields a condition bucket, never MS-numeric precision.
_GRADE_SYNONYMS: list[tuple[str, str]] = [
    ("about uncirculated", "AU"),
    ("almost uncirculated", "AU"),
    ("brilliant uncirculated", "UNC"),
    ("mint state", "UNC"),
    ("uncirculated", "UNC"),
    ("extremely fine", "XF"),
    ("extra fine", "XF"),
    ("very fine", "VF"),
    ("very good", "VG"),
    ("about good", "AG"),
    ("almost good", "AG"),
    ("fine", "F"),
    ("good", "G"),
]
# Abbreviation tokens (matched as whole words, case-insensitive).
_GRADE_ABBREV = {
    "ag": "AG",
    "g": "G",
    "vg": "VG",
    "f": "F",
    "vf": "VF",
    "xf": "XF",
    "ef": "XF",  # EF (English usage) == XF
    "au": "AU",
    "unc": "UNC",
    "bu": "UNC",  # brilliant uncirculated
    "ms": "UNC",  # mint state -> UNC bucket (numeric stripped)
}

_NUM_WORDS = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}

_YEAR_RE = re.compile(r"(1[5-9]\d\d|20\d\d)")
# The same, but as a standalone token in flat text: a year buried in a longer
# digit run (a slab cert number, a phone number) is not a date.
_YEAR_TOKEN_RE = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")

# A reader that hedges, refuses or negates has not given a reading. Every
# prompt in tiers.py tells the model to answer "unclear" when it cannot tell,
# so these words mean "no answer" — never material to mine a value out of.
_NO_READING_RE = re.compile(
    r"\b(unclear|unsure|uncertain|unreadable|illegible|cannot|unable|"
    r"impossible|not|no\s+way)\b|n't\b"
)


def _single_year(candidates: list[str]) -> int | None:
    """One distinct plausible year, or None. Two different years (a dual-dated
    1776-1976 coin, a statehood date beside the mint date) is an ambiguity the
    gate must escalate, not a tie to break by reading order."""
    distinct = set(candidates)
    if len(distinct) == 1:
        return int(next(iter(distinct)))
    return None


def canon_grade(text: str | None) -> str | None:
    """Map free grade text to one canonical bucket, or None if not certain.

    Handles paraphrases ("extremely fine" -> XF), abbreviations ("EF" -> XF),
    and strips MS/AU numerics to their bucket ("MS-63" -> UNC, "AU-58" -> AU).
    """
    if not text:
        return None
    low = text.lower()
    # A refusal or hedge is not a grade: "not good enough to determine the
    # grade" must never become G because it contains the word "good".
    if _NO_READING_RE.search(low):
        return None
    found: set[str] = set()
    # Phrase synonyms first (longest already ordered). Each matched phrase is
    # blanked so its words are not re-read as a second, shorter grade
    # ("extremely fine" is XF, not XF and F).
    for phrase, bucket in _GRADE_SYNONYMS:
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b")
        if pattern.search(low):
            found.add(bucket)
            low = pattern.sub(lambda m: " " * len(m.group(0)), low)
    # Abbreviations, incl. "MS63"/"AU-58"/"XF 45" (letters then optional digits).
    for m in re.finditer(r"\b([a-z]{1,3})\b", low):
        tok = m.group(1)
        if tok in _GRADE_ABBREV:
            found.add(_GRADE_ABBREV[tok])
    # Exactly one bucket, or nothing. "VF. Good eye appeal." names two; picking
    # either would be a guess, and grade is accepted on this reading alone.
    if len(found) == 1:
        return next(iter(found))
    return None


def parse_year_digits(text: str | None) -> int | None:
    """Parse a 4-digit year from a DIGIT-BY-DIGIT prose reading.

    Do NOT trust a bare year token: instead reconstruct the digit stream from
    both number-words ("one nine four three") and ASCII digits ("1 9 4 3" or
    "1943"), then take the plausible 4-digit year (15xx-19xx or 20xx) it forms.

    Returns None when no plausible year forms, when ANY digit was reported
    unclear (closing the gap around a missing digit would manufacture a year
    nobody read: "1, 9, unclear, 3 ... possibly 1943" is not 1931), or when
    the reading yields two different years.
    """
    if not text:
        return None
    low = text.lower()
    if _NO_READING_RE.search(low):
        return None
    # Tokenize into number-words and digit runs, in reading order.
    digits: list[str] = []
    for tok in re.findall(r"[a-z]+|\d+", low):
        if tok in _NUM_WORDS:
            digits.append(_NUM_WORDS[tok])
        elif tok.isdigit() and len(tok) <= 4:
            digits.extend(list(tok))
        # non-numeric words are separators, ignored; a digit run longer than
        # four is some other number (a cert, a catalogue id), never a date.
    stream = "".join(digits)
    return _single_year(_YEAR_RE.findall(stream))


def canon_mintmark(text: str | None) -> tuple[bool | None, str | None]:
    """Parse a mintmark statement into (present, letter).

    Returns:
      (True, "D")  -- a mintmark letter was affirmatively read
      (False, None)-- reader affirmatively saw NO mintmark
      (None, None) -- could not tell (unreadable)

    Conservative: an affirmative "no mintmark"/"none"/"absent"/"Philadelphia
    (no mark)" beats a stray letter; a letter is only taken from the allowed
    alphabet {P,D,S,O,CC,W}.
    """
    if not text:
        return None, None
    # A possessive is not a mint letter: "this coin's mintmark" has no S in it.
    low = re.sub(r"['\u2019]s\b", "", text.lower())
    # The prompt's own "cannot tell" answer, wherever it appears.
    if re.search(r"\b(unclear|unsure|uncertain|unreadable|illegible)\b", low):
        return None, None
    # Affirmative "no mintmark" statements.
    if re.search(
        r"\b(no|without|absent|none|no\s+mint\s*mark|lacks?)\b.*\bmint\s*mark\b"
        r"|\bmint\s*mark\b.*\b(absent|none|not\s+present|missing)\b"
        r"|\bno\s+mint\s*mark\b",
        low,
    ):
        return False, None
    # Explicit letter callouts: find the "mintmark" anchor and look for an
    # allowed token in a small window on either side ("mintmark is CC", "the D
    # mintmark", "mint mark: D"). CC is checked first (two-letter).
    anchor = re.search(r"mint\s*mark", low)
    if anchor is not None:
        lo = max(0, anchor.start() - 15)
        hi = min(len(low), anchor.end() + 15)
        window = low[lo:hi]
        seen = [
            mm
            for mm in MINTMARKS
            if re.search(r"\b" + re.escape(mm.lower()) + r"\b", window)
        ]
        if len(seen) == 1:
            return True, seen[0]
        if len(seen) > 1:
            # "Mintmark: S or D" — two letters is a hedge, not a reading.
            return None, None
    # A response that is just a bare allowed token ("D", "CC").
    bare = low.strip().strip(".:! ")
    for mm in MINTMARKS:
        if bare == mm.lower():
            return True, mm
    # "Philadelphia" with no letter -> P mint historically has no mark on many
    # issues; be conservative and treat as "saw none" rather than inventing P.
    if re.search(r"\bphiladelphia\b", low) and not re.search(r"\bmint\s*mark\b", low):
        return False, None
    return None, None


def find_mintmark_in_text(text: str | None) -> tuple[bool | None, str | None]:
    """OCR-side mintmark extraction from a flat legend transcription.

    Positions are unavailable, so this is deliberately conservative on the
    subset {D,S,O,CC,W} ('P' excluded — rarely stamped, collides with legend
    words). Over transcribed coin text:
      * exactly one distinct isolated allowed token -> (True, letter)
      * zero  -> (False, None): OCR read the coin and found no mintmark letter,
        a WEAK "no mark" vote (the common Philadelphia case). The agreement gate
        still requires the VLM to concur, and key-date years demand unanimity.
      * two or more distinct -> (None, None): ambiguous, no guess.
    """
    if not text or not text.strip():
        return None, None
    up = text.upper()
    tokens = re.findall(r"\b[A-Z]{1,2}\b", up)
    candidate_set = {"D", "S", "O", "CC", "W"}
    distinct = {t for t in tokens if t in candidate_set}
    if len(distinct) == 1:
        return True, next(iter(distinct))
    if len(distinct) == 0:
        return False, None
    return None, None


def canon_series(text: str | None, known: list[str]) -> str | None:
    """Canonicalize a series reading against known series + the alias table.

    ``known`` is the live list of canonical series names (from loaded sets +
    coins in the ledger). Matching is case-insensitive and substring-aware
    (the VLM often wraps the name in a sentence). Longest candidate wins.
    Returns None when nothing matches — never a guessed series.
    """
    if not text:
        return None
    low = text.lower()
    candidates: dict[str, str] = {}
    for name in known:
        if name:
            candidates[name.lower()] = name
    for phrase, canonical in _SERIES_ALIASES.items():
        candidates.setdefault(phrase, canonical)
    for phrase in sorted(candidates, key=len, reverse=True):
        if re.search(r"\b" + re.escape(phrase) + r"\b", low):
            return candidates[phrase]
    return None


def find_year_in_text(text: str | None) -> int | None:
    """Extract the one plausible 4-digit year from flat OCR text.

    A standalone token only (not four digits inside a longer number), and
    only when the text carries a single distinct year — two different dates
    on one coin are escalated by the gate, not resolved by reading order.
    """
    if not text:
        return None
    return _single_year(_YEAR_TOKEN_RE.findall(text))


# --- Denomination ----------------------------------------------------------
# Same vocabulary/order as quickadd._DENOMINATIONS (longest phrase first).
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


def canon_denomination(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for phrase, canonical in _DENOMINATIONS:
        if re.search(r"\b" + re.escape(phrase) + r"\b", low):
            return canonical
    return None


def canon_country(text: str | None) -> str | None:
    """Only the US variants are canonicalized (to 'US', the ledger default).

    Anything else returns None rather than a guessed ISO code — country is not
    gate-critical and we never fabricate it.
    """
    if not text:
        return None
    low = text.lower()
    if re.search(r"\b(u\.?s\.?a?\.?|united states(?: of america)?)\b", low):
        return "US"
    return None


def json_string_values(text: str | None) -> str:
    """Concatenate all string leaf values from any JSON object embedded in text.

    Used so downstream canonicalizers ignore KEYS entirely (Qwen renames them)
    and normalize on VALUES. Returns '' when no JSON object is found.
    """
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    try:
        obj = json.loads(text[start : end + 1])
    except Exception:
        return ""
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)):
            out.append(str(node))

    walk(obj)
    return " ".join(out)
