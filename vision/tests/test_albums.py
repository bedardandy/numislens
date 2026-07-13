from __future__ import annotations

from numislens_vision import albums, endpoints
from numislens_vision.config import VisionConfig


def _cfg(gemma_url=None):
    return VisionConfig(
        daemon_url="http://daemon",
        token="t",
        ocr_urls=("http://ocr1",),
        ocr_model="ocr-model",
        vlm_url="http://vlm",
        vlm_model="vlm-model",
        gemma_url=gemma_url,
        gemma_model="gemma-model",
    )


def _wire(monkeypatch, *, classify="yes", ocr="", vlm_fill="", gemma_fill=""):
    def fake_ocr(ocr_urls, model, prompt, images, *, timeout, max_tokens=512):
        return ocr, ocr_urls[0]

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        if "coin folder or coin album" in prompt:
            return classify
        if "Labels:" in prompt:
            return gemma_fill if base_url == "http://gemma" else vlm_fill
        return ""

    monkeypatch.setattr(endpoints, "ocr_with_failover", fake_ocr)
    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)


_OCR = "LINCOLN CENTS 1941-1958\n1943 D\n1943 S\n1943 P"


def test_analyze_page_filled_empty_unclear(monkeypatch):
    _wire(
        monkeypatch,
        ocr=_OCR,
        vlm_fill="1943 D => filled\n1943 S => empty\n1943 P => unclear",
    )
    page = albums.analyze_page(_cfg(), "Zm9v")
    assert page.page_type == "page"
    assert page.page_title == "LINCOLN CENTS 1941-1958"
    states = {s["label_text"]: s["fill_state"] for s in page.slots}
    assert states["1943 D"] == "filled"
    assert states["1943 S"] == "empty"
    assert states["1943 P"] == "uncertain"  # 'unclear' never becomes filled/empty


def test_analyze_page_echo_mismatch_is_uncertain(monkeypatch):
    # VLM echoes a label that does not match any OCR label -> that slot uncertain.
    _wire(
        monkeypatch,
        ocr="1943 D",
        vlm_fill="1999 X => filled",
    )
    page = albums.analyze_page(_cfg(), "Zm9v")
    assert len(page.slots) == 1
    assert page.slots[0]["fill_state"] == "uncertain"


def test_analyze_page_not_a_page_short_circuits(monkeypatch):
    _wire(monkeypatch, classify="no", ocr=_OCR, vlm_fill="1943 D => filled")
    page = albums.analyze_page(_cfg(), "Zm9v")
    assert page.page_type == "not_a_page"
    assert page.slots == []


def test_analyze_page_gemma_disagreement_is_uncertain(monkeypatch):
    _wire(
        monkeypatch,
        ocr="1943 D",
        vlm_fill="1943 D => filled",
        gemma_fill="1943 D => empty",  # third voter disagrees
    )
    page = albums.analyze_page(_cfg(gemma_url="http://gemma"), "Zm9v")
    assert page.slots[0]["fill_state"] == "uncertain"


def test_analyze_page_gemma_agreement_accepts(monkeypatch):
    _wire(
        monkeypatch,
        ocr="1943 D",
        vlm_fill="1943 D => filled",
        gemma_fill="1943 D => filled",
    )
    page = albums.analyze_page(_cfg(gemma_url="http://gemma"), "Zm9v")
    assert page.slots[0]["fill_state"] == "filled"


def test_analyze_page_ocr_down_yields_no_slots(monkeypatch):
    def fake_ocr(ocr_urls, model, prompt, images, *, timeout, max_tokens=512):
        raise endpoints.AllOCRDown(ocr_urls, ["down"])

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        return "yes"

    monkeypatch.setattr(endpoints, "ocr_with_failover", fake_ocr)
    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)
    page = albums.analyze_page(_cfg(), "Zm9v")
    assert page.page_type == "page"
    assert page.slots == []


# ---------------------------------------------------------------------------
# analyze_import against a mocked daemon
# ---------------------------------------------------------------------------

class FakeAlbumClient:
    def __init__(self, pages):
        self._state = {"pages": pages}
        self.posted = []

    def get_import(self, import_id):
        return self._state

    def get_page_image(self, import_id, page_id):
        return b"fake-image-bytes"

    def post_analysis(self, import_id, page_id, body):
        self.posted.append((page_id, body))
        return {"ok": True}


def test_analyze_import_posts_unanalyzed_only(monkeypatch):
    _wire(monkeypatch, ocr="1943 D", vlm_fill="1943 D => filled")
    client = FakeAlbumClient(
        [
            {"page_id": 1, "analyzed_at": None},
            {"page_id": 2, "analyzed_at": "2026-07-13T00:00:00+00:00"},  # skip
        ]
    )
    results = albums.analyze_import(_cfg(), 7, client=client)
    assert len(results) == 1
    assert results[0]["page_id"] == 1
    assert results[0]["slot_count"] == 1
    # Only the un-analyzed page was posted back.
    assert [pid for pid, _ in client.posted] == [1]
    _pid, body = client.posted[0]
    assert body["page_type"] == "page"
    assert body["slots"][0]["fill_state"] == "filled"
