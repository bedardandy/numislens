from __future__ import annotations

from numislens_vision.config import VisionConfig
from numislens_vision.writeback import apply_writeback


def _cfg():
    return VisionConfig(
        daemon_url="http://d", token="t",
        ocr_urls=("http://o",), ocr_model="o", vlm_url="http://v", vlm_model="v",
        gemma_url=None, gemma_model="g",
    )


class FakeDaemon:
    def __init__(self, patch_result=None):
        self.calls: list = []
        self._patch_result = patch_result or {"written": {}, "skipped": {}}

    def patch_identification(self, accession, fields):
        self.calls.append(("patch", accession, dict(fields)))
        return self._patch_result

    def record_appraisal(self, accession, body):
        self.calls.append(("appraise", accession, dict(body)))
        return {"appraisal_id": len(self.calls)}

    def mark_stale_digest(self, accession, reason, source_note=None):
        self.calls.append(("stale", accession, reason))
        return {"total_marked": 1}


def _result(accepted, escalations=None, tiers_used=None):
    return {
        "accession": "NL-000001",
        "accepted": accepted,
        "escalations": escalations or [],
        "tiers_used": tiers_used or ["ocr:http://o", "vlm:http://v"],
        "tiers_unavailable": [],
    }


def test_writeback_fills_null_and_records_grade():
    fake = FakeDaemon(patch_result={
        "written": {"series": "Peace Dollar", "year": 1921, "grade_bucket": "XF",
                    "grade_source": "local-vlm"},
        "skipped": {},
    })
    result = _result({
        "series": "Peace Dollar", "year": 1921, "mintmark": None,
        "grade_bucket": "XF", "grade_confidence": "photo-grade",
    })
    report = apply_writeback(_cfg(), result, client=fake)

    patch_call = next(c for c in fake.calls if c[0] == "patch")
    assert patch_call[2]["series"] == "Peace Dollar"
    assert patch_call[2]["grade_bucket"] == "XF"
    assert patch_call[2]["grade_source"] == "local-vlm"  # grade is single-tier
    assert "mintmark" not in patch_call[2]  # None -> not written

    appraise_call = next(c for c in fake.calls if c[0] == "appraise")
    assert appraise_call[2]["appraised_by"] == "vision:ocr+vlm"
    assert appraise_call[2]["grade_bucket"] == "XF"
    assert appraise_call[2]["confidence"] == 0.5
    assert report["grade_appraisal"] == "XF"
    assert report["escalation"] is None


def test_writeback_reports_skips_without_overwrite():
    fake = FakeDaemon(patch_result={
        "written": {"mintmark": "D"},
        "skipped": {"series": "Morgan Dollar", "year": 1889},
    })
    result = _result({
        "series": "Peace Dollar", "year": 1921, "mintmark": "D",
        "grade_bucket": None, "grade_confidence": None,
    })
    report = apply_writeback(_cfg(), result, client=fake)
    assert report["written"] == {"mintmark": "D"}
    assert report["skipped"] == {"series": "Morgan Dollar", "year": 1889}
    # No grade accepted -> no grade appraisal.
    assert report["grade_appraisal"] is None
    assert not any(c[0] == "appraise" for c in fake.calls)


def test_writeback_escalation_notes_and_marks_stale():
    fake = FakeDaemon()
    escalations = [
        {"field": "year", "readings": {"ocr": 1943, "vlm": 1948}, "note": "disagree"},
        {"field": "mintmark", "readings": {"ocr": "D", "vlm": "NONE"}, "note": "disagree"},
    ]
    result = _result(
        {"series": "Lincoln Wheat Cent", "year": None, "mintmark": None,
         "grade_bucket": "F", "grade_confidence": "photo-grade"},
        escalations=escalations,
    )
    report = apply_writeback(_cfg(), result, client=fake)

    kinds = [c[0] for c in fake.calls]
    # Grade appraisal must precede the escalation stale-mark so the stale flag
    # survives (record_appraisal clears staleness).
    grade_idx = next(i for i, c in enumerate(fake.calls)
                     if c[0] == "appraise" and c[2].get("grade_bucket"))
    esc_idx = next(i for i, c in enumerate(fake.calls)
                   if c[0] == "appraise" and c[2]["appraised_by"] == "vision:escalation")
    stale_idx = kinds.index("stale")
    assert grade_idx < esc_idx < stale_idx

    esc_call = fake.calls[esc_idx]
    assert "VISION ESCALATION" in esc_call[2]["rationale"]
    assert "1948" in esc_call[2]["rationale"]  # readings carried verbatim
    stale_call = fake.calls[stale_idx]
    assert "vision escalation: mintmark,year" in stale_call[2]
    assert report["escalation"]["fields"] == "mintmark,year"


def test_writeback_appraised_by_cross_vote_with_gemma():
    fake = FakeDaemon(patch_result={"written": {"year": 1943}, "skipped": {}})
    result = _result(
        {"series": None, "year": 1943, "mintmark": None,
         "grade_bucket": "VF", "grade_confidence": "photo-grade"},
        tiers_used=["ocr:http://o", "vlm:http://v", "gemma:http://g"],
    )
    apply_writeback(_cfg(), result, client=fake)
    appraise = next(c for c in fake.calls if c[0] == "appraise")
    assert appraise[2]["appraised_by"] == "vision:cross-vote"
