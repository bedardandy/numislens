from __future__ import annotations

import pytest

from numislens_vision import worker
from numislens_vision.config import VisionConfig


def _cfg():
    return VisionConfig(
        daemon_url="http://d", token="t",
        ocr_urls=("http://o",), ocr_model="o", vlm_url="http://v", vlm_model="v",
        gemma_url=None, gemma_model="g",
    )


class FakeClient:
    def __init__(self, coins, details):
        self._coins = coins
        self._details = details  # accession -> full coin dict

    def list_coins(self):
        return self._coins

    def get_coin(self, accession):
        return self._details[accession]


def _coin(acc, series=None, year=None, images=(), appraisals=()):
    return {
        "accession_no": acc,
        "series": series,
        "year": year,
        "coin_images": [{"kind": k, "content_hash": f"h-{k}"} for k in images],
        "appraisals": [{"appraised_by": a} for a in appraisals],
    }


def test_select_pending_filters():
    coins = [
        _coin("NL-000001"),                    # unidentified, but no images
        _coin("NL-000002"),                    # unidentified + images -> PENDING
        _coin("NL-000003"),                    # identified -> skip
        _coin("NL-000004"),                    # unidentified + images + vision appraisal -> skip
    ]
    details = {
        "NL-000001": _coin("NL-000001", images=()),
        "NL-000002": _coin("NL-000002", images=("obverse", "reverse")),
        "NL-000003": _coin("NL-000003", series="Peace Dollar", year=1921, images=("obverse",)),
        "NL-000004": _coin("NL-000004", images=("obverse",), appraisals=("vision:cross-vote",)),
    }
    # list_coins carries the identify state; NL-000003 has series/year set.
    coins[2] = _coin("NL-000003", series="Peace Dollar", year=1921)
    client = FakeClient(coins, details)
    assert worker.select_pending(client) == ["NL-000002"]


def test_process_requires_exactly_one_target():
    with pytest.raises(ValueError):
        worker.process(_cfg(), client=FakeClient([], {}))


def test_process_one_calls_identify_and_writeback(monkeypatch):
    seen = {}

    def fake_identify(cfg, acc, client=None):
        seen["identify"] = acc
        return {"accession": acc, "accepted": {"year": 1943}, "escalations": [],
                "tiers_used": ["ocr:x", "vlm:y"], "tiers_unavailable": []}

    def fake_writeback(cfg, result, client=None):
        seen["writeback"] = result["accession"]
        return {"accession": result["accession"], "written": {"year": 1943},
                "skipped": {}, "grade_appraisal": None, "escalation": None}

    monkeypatch.setattr(worker, "identify", fake_identify)
    monkeypatch.setattr(worker, "apply_writeback", fake_writeback)
    out = worker.process(_cfg(), accession="NL-000009", client=object(), printer=lambda *_: None)
    assert seen == {"identify": "NL-000009", "writeback": "NL-000009"}
    assert len(out) == 1


def test_process_pending_iterates(monkeypatch):
    coins = [_coin("NL-000002"), _coin("NL-000005")]
    details = {
        "NL-000002": _coin("NL-000002", images=("obverse",)),
        "NL-000005": _coin("NL-000005", images=("obverse",)),
    }
    client = FakeClient(coins, details)
    processed = []
    monkeypatch.setattr(worker, "identify",
                        lambda cfg, acc, client=None: {"accession": acc, "accepted": {},
                        "escalations": [], "tiers_used": [], "tiers_unavailable": []})
    monkeypatch.setattr(worker, "apply_writeback",
                        lambda cfg, result, client=None: processed.append(result["accession"]) or
                        {"written": {}, "skipped": {}, "grade_appraisal": None, "escalation": None})
    worker.process(_cfg(), pending=True, client=client, printer=lambda *_: None)
    assert processed == ["NL-000002", "NL-000005"]


def test_status_counts():
    coins = [
        _coin("NL-000001", series="Peace Dollar", year=1921),  # identified, no img
        _coin("NL-000002"),                                    # pending
        _coin("NL-000003"),                                    # processed already
    ]
    details = {
        "NL-000001": _coin("NL-000001", series="Peace Dollar", year=1921),
        "NL-000002": _coin("NL-000002", images=("obverse",)),
        "NL-000003": _coin("NL-000003", images=("obverse",), appraisals=("vision:ocr+vlm",)),
    }
    st = worker.status(_cfg(), client=FakeClient(coins, details))
    assert st["total_coins"] == 3
    assert st["with_images"] == 2
    assert st["unidentified"] == 2
    assert st["vision_processed"] == 1
    assert st["pending"] == 1
