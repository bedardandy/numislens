"""Tests for the exact dollar-string -> integer-cents parser."""

from __future__ import annotations

import pytest

from numislens_core.money import parse_dollars_to_cents


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4", 400),
        ("$4", 400),
        (" $4 ", 400),
        ("19.99", 1999),
        ("$1,234.56", 123456),
        ("1234567", 123456700),
        ("0.05", 5),
        (".5", 50),
        ("12.7", 1270),
        ("1,23", 12300),  # commas stripped without grouping validation (legacy)
    ],
)
def test_parses_exact_cents(raw: str, expected: int) -> None:
    assert parse_dollars_to_cents(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "$",
        "50.",  # trailing dot: the regex never accepted it, keep refusing
        "-5",
        "$-5",
        "1.999",  # three decimal places: refuse rather than round
        "abc",
        "4 dollars",
        None,
        19.99,  # a float is exactly what this parser exists to avoid
    ],
)
def test_refuses_non_exact_inputs(raw) -> None:
    with pytest.raises(ValueError):
        parse_dollars_to_cents(raw)
