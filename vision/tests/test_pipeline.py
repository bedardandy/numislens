from __future__ import annotations

from numislens_vision import endpoints, pipeline, tiers
from numislens_vision.config import VisionConfig


def _cfg(gemma_url=None):
    return VisionConfig(
        daemon_url="http://daemon",
        token="t",
        ocr_urls=("http://ocr1", "http://ocr2"),
        ocr_model="ocr-model",
        vlm_url="http://vlm",
        vlm_model="vlm-model",
        gemma_url=gemma_url,
        gemma_model="gemma-model",
    )


class FakeClient:
    def __init__(self, coin, *, series=None, key_years=None):
        self._coin = coin
        self._series = series or []
        self._key_years = key_years or set()

    def get_coin(self, accession):
        return self._coin

    def get_image_bytes(self, accession, content_hash):
        return b"fake-image-bytes"

    def known_series(self):
        return self._series

    def key_date_years(self):
        return self._key_years


def _coin(images=("obverse", "reverse")):
    return {
        "accession_no": "NL-000001",
        "coin_images": [
            {"kind": k, "content_hash": f"hash-{k}"} for k in images
        ],
    }


def _wire_vlm(monkeypatch, *, series_txt, date_txt, mint_txt, grade_txt, ocr_txt):
    def fake_ocr(ocr_urls, model, prompt, images, *, timeout, max_tokens=512):
        return ocr_txt, ocr_urls[0]

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        if "ONE DIGIT AT A TIME" in prompt:
            return date_txt
        if "mintmark" in prompt.lower():
            return mint_txt
        if "CONDITION" in prompt:
            return grade_txt
        return series_txt

    monkeypatch.setattr(endpoints, "ocr_with_failover", fake_ocr)
    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)


def test_pipeline_full_agreement_accepts(monkeypatch):
    _wire_vlm(
        monkeypatch,
        ocr_txt="LIBERTY 1943 IN GOD WE TRUST",
        series_txt="Series: Lincoln Wheat Cent\nDenomination: cent\nCountry: USA",
        date_txt="first digit 1, then 9, 4, 3",
        mint_txt="Mintmark: none",
        grade_txt="extremely fine",
    )
    client = FakeClient(_coin(), series=["Lincoln Wheat Cent"])
    result = pipeline.identify(_cfg(), "NL-000001", client=client)
    acc = result["accepted"]
    assert acc["year"] == 1943
    assert acc["series"] == "Lincoln Wheat Cent"
    assert acc["mintmark"] is None  # both saw no mark
    assert acc["grade_bucket"] == "XF"
    assert acc["grade_confidence"] == "photo-grade"
    assert result["escalations"] == []
    assert any(t.startswith("ocr:") for t in result["tiers_used"])
    assert any(t.startswith("vlm:") for t in result["tiers_used"])
    assert any(t.startswith("gemma:") for t in result["tiers_unavailable"])


def test_pipeline_year_disagreement_escalates(monkeypatch):
    _wire_vlm(
        monkeypatch,
        ocr_txt="LIBERTY 1943",
        series_txt="Series: Lincoln Wheat Cent",
        date_txt="1, 9, 4, 8",  # VLM reads 1948, OCR read 1943
        mint_txt="Mintmark: none",
        grade_txt="fine",
    )
    client = FakeClient(_coin(), series=["Lincoln Wheat Cent"])
    result = pipeline.identify(_cfg(), "NL-000001", client=client)
    assert result["accepted"]["year"] is None
    fields = {e["field"] for e in result["escalations"]}
    assert "year" in fields
    esc = next(e for e in result["escalations"] if e["field"] == "year")
    assert esc["readings"]["ocr"] == 1943 and esc["readings"]["vlm"] == 1948


def test_pipeline_key_date_disagreement_escalates(monkeypatch):
    # OCR reads 1932-D, VLM reads 1932-S: key year, mints differ -> escalate.
    _wire_vlm(
        monkeypatch,
        ocr_txt="LIBERTY 1932 D",
        series_txt="Series: Washington Quarter",
        date_txt="1 9 3 2",
        mint_txt="Mintmark: S",
        grade_txt="very fine",
    )
    client = FakeClient(_coin(), series=["Washington Quarter"], key_years={1932})
    result = pipeline.identify(_cfg(), "NL-000001", client=client)
    fields = {e["field"] for e in result["escalations"]}
    assert "mintmark" in fields
    assert result["accepted"]["mintmark"] is None


def test_pipeline_ocr_down_marks_tier_unavailable(monkeypatch):
    def fake_ocr(ocr_urls, model, prompt, images, *, timeout, max_tokens=512):
        raise endpoints.AllOCRDown(ocr_urls, ["refused", "refused"])

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        if "ONE DIGIT AT A TIME" in prompt:
            return "1 9 4 3"
        if "mintmark" in prompt.lower():
            return "Mintmark: none"
        if "CONDITION" in prompt:
            return "fine"
        return "Series: Lincoln Wheat Cent"

    monkeypatch.setattr(endpoints, "ocr_with_failover", fake_ocr)
    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)
    client = FakeClient(_coin(), series=["Lincoln Wheat Cent"])
    result = pipeline.identify(_cfg(), "NL-000001", client=client)
    assert any(t.startswith("ocr:") for t in result["tiers_unavailable"])
    # With no OCR vote, year cannot pass the two-tier gate -> escalate.
    assert result["accepted"]["year"] is None
    assert "year" in {e["field"] for e in result["escalations"]}


def test_pipeline_no_images_fails_loud(monkeypatch):
    client = FakeClient(_coin(images=()))
    result = pipeline.identify(_cfg(), "NL-000001", client=client)
    assert result["tiers_used"] == []
    assert "images" in {e["field"] for e in result["escalations"]}
    assert all(v is None for k, v in result["accepted"].items())


def test_pipeline_gemma_third_voter_breaks_tie(monkeypatch):
    # OCR 1943, VLM 1948, Gemma 1943 -> 2-of-3 accepts 1943.
    def fake_ocr(ocr_urls, model, prompt, images, *, timeout, max_tokens=512):
        return "LIBERTY 1943", ocr_urls[0]

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        is_gemma = base_url == "http://gemma"
        if "ONE DIGIT AT A TIME" in prompt:
            return "1 9 4 3" if is_gemma else "1 9 4 8"
        if "mintmark" in prompt.lower():
            return "Mintmark: none"
        if "CONDITION" in prompt:
            return "fine"
        return "Series: Lincoln Wheat Cent"

    monkeypatch.setattr(endpoints, "ocr_with_failover", fake_ocr)
    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)
    client = FakeClient(_coin(), series=["Lincoln Wheat Cent"])
    result = pipeline.identify(_cfg(gemma_url="http://gemma"), "NL-000001", client=client)
    assert result["accepted"]["year"] == 1943
    assert any(t.startswith("gemma:") for t in result["tiers_used"])
