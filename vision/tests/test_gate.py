from __future__ import annotations

from numislens_vision.gate import run_gate
from numislens_vision.tiers import OCRReading, VLMReading


def _ocr(year=None, present=None, letter=None, available=True):
    return OCRReading(
        available=available, url_used="http://ocr", text="x",
        year=year, mintmark_present=present, mintmark_letter=letter,
    )


def _vlm(year=None, present=None, letter=None, series=None, grade=None, available=True):
    return VLMReading(
        available=available, series=series, year=year,
        mintmark_present=present, mintmark_letter=letter, grade_bucket=grade,
        raw={"series": "s", "date": "d", "mintmark": "m", "grade": "g"},
    )


def _no_gemma():
    return VLMReading(available=False, error="gemma not configured")


def _fields_escalated(result):
    return {e["field"] for e in result["escalations"]}


def test_year_agreement_accepts():
    r = run_gate(_ocr(year=1943), _vlm(year=1943, series="Lincoln Wheat Cent", grade="XF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["year"] == 1943
    assert "year" not in _fields_escalated(r)


def test_year_disagreement_escalates():
    r = run_gate(_ocr(year=1943), _vlm(year=1948, series="Lincoln Wheat Cent", grade="XF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["year"] is None
    assert "year" in _fields_escalated(r)
    esc = next(e for e in r["escalations"] if e["field"] == "year")
    assert esc["readings"] == {"ocr": 1943, "vlm": 1948}


def test_ocr_unreadable_year_escalates_in_two_tier():
    # OCR tier up but could not read the year -> no agreement -> escalate.
    r = run_gate(_ocr(year=None), _vlm(year=1943, series="Morgan Dollar", grade="VF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["year"] is None
    assert "year" in _fields_escalated(r)


def test_mintmark_both_none_accepts_as_no_mark():
    r = run_gate(_ocr(year=1943, present=False), _vlm(year=1943, present=False,
                 series="Lincoln Wheat Cent", grade="XF"), _no_gemma(), key_date_years=set())
    # Both affirmatively saw no mintmark -> accepted mintmark is None (no mark).
    assert r["accepted"]["mintmark"] is None
    assert "mintmark" not in _fields_escalated(r)


def test_mintmark_agreement_letter():
    r = run_gate(_ocr(year=1885, present=True, letter="CC"),
                 _vlm(year=1885, present=True, letter="CC", series="Morgan Dollar", grade="AU"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["mintmark"] == "CC"


def test_mintmark_disagreement_escalates():
    r = run_gate(_ocr(year=1943, present=True, letter="D"),
                 _vlm(year=1943, present=False, series="Lincoln Wheat Cent", grade="XF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["mintmark"] is None
    assert "mintmark" in _fields_escalated(r)


def test_series_accepts_from_vlm():
    r = run_gate(_ocr(year=1921), _vlm(year=1921, series="Peace Dollar", grade="XF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["series"] == "Peace Dollar"


def test_series_unresolved_escalates():
    r = run_gate(_ocr(year=1921), _vlm(year=1921, series=None, grade="XF"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["series"] is None
    assert "series" in _fields_escalated(r)


def test_grade_photo_grade_flag():
    r = run_gate(_ocr(year=1921), _vlm(year=1921, series="Peace Dollar", grade="AU"),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["grade_bucket"] == "AU"
    assert r["accepted"]["grade_confidence"] == "photo-grade"


def test_grade_unreadable_escalates():
    r = run_gate(_ocr(year=1921), _vlm(year=1921, series="Peace Dollar", grade=None),
                 _no_gemma(), key_date_years=set())
    assert r["accepted"]["grade_bucket"] is None
    assert "grade_bucket" in _fields_escalated(r)


def test_key_date_requires_unanimity_two_tier_agree():
    # 1932 is a key-date year (1932-D/S quarters). Two available tiers agree ->
    # unanimous -> accepted even under the strict key-date rule.
    r = run_gate(_ocr(year=1932, present=True, letter="D"),
                 _vlm(year=1932, present=True, letter="D",
                      series="Washington Quarter", grade="VF"),
                 _no_gemma(), key_date_years={1932})
    assert r["accepted"]["year"] == 1932
    assert r["accepted"]["mintmark"] == "D"


def test_key_date_escalates_on_any_disagreement():
    # Non-key years would 2-of-3 or unanimity-of-2; here a key year with a
    # mintmark disagreement must escalate (the 100x case).
    r = run_gate(_ocr(year=1932, present=True, letter="D"),
                 _vlm(year=1932, present=True, letter="S",
                      series="Washington Quarter", grade="VF"),
                 _no_gemma(), key_date_years={1932})
    assert r["accepted"]["mintmark"] is None
    esc = next(e for e in r["escalations"] if e["field"] == "mintmark")
    assert "key-date" in esc["note"]


def test_gemma_two_of_three_wins_non_keydate():
    gemma = VLMReading(available=True, year=1943, mintmark_present=False,
                       raw={"date": "d", "mintmark": "m"})
    r = run_gate(_ocr(year=1943, present=False),
                 _vlm(year=1948, present=False, series="Lincoln Wheat Cent", grade="XF"),
                 gemma, key_date_years=set())
    # ocr=1943, vlm=1948, gemma=1943 -> 2-of-3 -> 1943.
    assert r["accepted"]["year"] == 1943


def test_gemma_three_way_split_escalates():
    gemma = VLMReading(available=True, year=1950, mintmark_present=None,
                       raw={"date": "d", "mintmark": "m"})
    r = run_gate(_ocr(year=1943), _vlm(year=1948, series="Lincoln Wheat Cent", grade="XF"),
                 gemma, key_date_years=set())
    assert r["accepted"]["year"] is None
    assert "year" in _fields_escalated(r)


def test_key_date_three_tier_needs_all_agree():
    # Key year, gemma missing its reading -> not all available agree -> escalate.
    gemma = VLMReading(available=True, year=None, mintmark_present=True, mintmark_letter="D",
                       raw={"date": "d", "mintmark": "m"})
    r = run_gate(_ocr(year=1932, present=True, letter="D"),
                 _vlm(year=1932, present=True, letter="D",
                      series="Washington Quarter", grade="VF"),
                 gemma, key_date_years={1932})
    assert r["accepted"]["year"] is None
    assert "year" in _fields_escalated(r)
