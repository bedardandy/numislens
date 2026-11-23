from __future__ import annotations

from numislens_vision import canon


def test_grade_paraphrase_extremely_fine_to_xf():
    assert canon.canon_grade("This coin is extremely fine.") == "XF"


def test_grade_abbrev_ef_to_xf():
    assert canon.canon_grade("EF") == "XF"


def test_grade_strips_ms_numeric_to_unc_bucket():
    # Honesty rule: no MS-numerics survive; MS-63 collapses to the UNC bucket.
    assert canon.canon_grade("MS-63") == "UNC"
    assert canon.canon_grade("about uncirculated, maybe AU-58") == "AU"


def test_grade_unparseable_is_none():
    assert canon.canon_grade("no idea, blurry") is None
    assert canon.canon_grade("") is None


def test_digit_by_digit_words():
    assert canon.parse_year_digits("first digit one, then nine, four, three") == 1943


def test_digit_by_digit_spaced_digits():
    assert canon.parse_year_digits("1 9 4 3") == 1943


def test_digit_by_digit_from_run():
    assert canon.parse_year_digits("the digits are 1943") == 1943


def test_digit_by_digit_unreadable():
    assert canon.parse_year_digits("unclear, cannot read the date") is None


def test_mintmark_letter():
    present, letter = canon.canon_mintmark("Mintmark: D")
    assert present is True and letter == "D"


def test_mintmark_none_affirmative():
    present, letter = canon.canon_mintmark("Mintmark: none")
    assert present is False and letter is None


def test_mintmark_cc_two_letter():
    present, letter = canon.canon_mintmark("the mint mark is CC")
    assert present is True and letter == "CC"


def test_mintmark_unclear():
    present, letter = canon.canon_mintmark("Mintmark: unclear")
    assert present is None and letter is None


def test_series_alias_canonicalizes():
    assert canon.canon_series("a lincoln wheat penny", []) == "Lincoln Wheat Cent"


def test_series_from_known_list():
    known = ["Washington Quarter", "Morgan Dollar"]
    assert canon.canon_series("looks like a Washington Quarter to me", known) == (
        "Washington Quarter"
    )


def test_series_unresolved_is_none():
    assert canon.canon_series("some foreign token", []) is None


def test_ocr_mintmark_single_isolated_letter():
    present, letter = canon.find_mintmark_in_text("LIBERTY 1943 D IN GOD WE TRUST")
    assert present is True and letter == "D"


def test_ocr_mintmark_ambiguous_is_none():
    # Two distinct candidate letters -> ambiguous -> no guess.
    present, letter = canon.find_mintmark_in_text("D S O legends everywhere")
    assert present is None and letter is None


def test_ocr_mintmark_zero_candidates_is_weak_none():
    # OCR read the coin but isolated no mintmark letter -> weak "no mark" vote.
    present, letter = canon.find_mintmark_in_text("LIBERTY 1943 IN GOD WE TRUST")
    assert present is False and letter is None


def test_json_string_values_ignores_keys():
    # Qwen renamed keys; we canonicalize on VALUES regardless of key names.
    blob = '{"coin_type": "Lincoln Wheat Cent", "face": "one cent"}'
    vals = canon.json_string_values(blob)
    assert "Lincoln Wheat Cent" in vals
    assert canon.canon_series(vals, []) == "Lincoln Wheat Cent"
    assert canon.canon_denomination(vals) == "cent"


def test_country_us_variants():
    assert canon.canon_country("United States of America") == "US"
    assert canon.canon_country("USA") == "US"
    assert canon.canon_country("Canada") is None


# --- a hedge, refusal or ambiguity is never a reading ----------------------


def test_grade_refusal_is_not_a_grade():
    for text in (
        "The image is not good enough to determine the grade",
        "Cannot determine, e.g. due to glare",
        "Unclear - too much glare to judge wear",
        "XF. Not quite about uncirculated.",
    ):
        assert canon.canon_grade(text) is None, text


def test_grade_with_two_buckets_is_ambiguous():
    assert canon.canon_grade("VF. Good eye appeal.") is None
    assert canon.canon_grade("XF - fine hairlines on the cheek") is None
    assert canon.canon_grade("VF to XF") is None


def test_grade_ladder_echo_still_canonicalizes():
    # The model often echoes the prompt's own ladder gloss.
    assert canon.canon_grade("G (heavy wear, outlines only)") == "G"
    assert canon.canon_grade("UNC (no wear)") == "UNC"
    assert canon.canon_grade("About Uncirculated") == "AU"
    assert canon.canon_grade("MS-63") == "UNC"


def test_year_with_an_unclear_digit_is_none():
    assert canon.parse_year_digits(
        "first digit: 1, second digit: 9, third digit: unclear (4 or 9), "
        "fourth digit: 3"
    ) is None
    assert canon.parse_year_digits("1 9 unclear 2 1") is None


def test_year_ignores_long_digit_runs_and_rejects_two_dates():
    assert canon.parse_year_digits("PCGS 4019432055 MS64 1881 S") == 1881
    assert canon.parse_year_digits("1776-1976") is None
    assert canon.parse_year_digits("digits 1, 9, 4, 3. The year is 1943.") == 1943


def test_ocr_year_is_a_standalone_token_and_unique():
    assert canon.find_year_in_text("LIBERTY 1943 IN GOD WE TRUST") == 1943
    assert canon.find_year_in_text("CERT 4019432055") is None
    assert canon.find_year_in_text("UNITED STATES 1776-1976 QUARTER DOLLAR") is None
    assert canon.find_year_in_text("DELAWARE 1787 THE FIRST STATE 1999") is None


def test_mintmark_possessive_and_hedges_are_not_letters():
    assert canon.canon_mintmark("This coin's mintmark is unclear.") == (None, None)
    assert canon.canon_mintmark("Mintmark: S or D") == (None, None)
    assert canon.canon_mintmark("The coin's mintmark is O") == (True, "O")
    assert canon.canon_mintmark("Mintmark: D") == (True, "D")
    assert canon.canon_mintmark("Mintmark: none") == (False, None)
