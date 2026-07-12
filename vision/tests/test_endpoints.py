from __future__ import annotations

import pytest

from numislens_vision import endpoints
from numislens_vision.endpoints import AllOCRDown, EndpointError, Image64


def test_ocr_failover_second_box(monkeypatch):
    calls = []

    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        calls.append(base_url)
        if base_url == "http://box1":
            raise EndpointError(f"connect error to {base_url}: refused")
        return "LIBERTY 1943"

    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)
    text, url = endpoints.ocr_with_failover(
        ("http://box1", "http://box2"), "m", "p", [], timeout=1.0
    )
    assert url == "http://box2"
    assert "1943" in text
    assert calls == ["http://box1", "http://box2"]


def test_ocr_all_down_fails_loud(monkeypatch):
    def fake_chat(base_url, model, prompt, images, *, timeout, max_tokens=512):
        raise EndpointError(f"connect error to {base_url}: refused")

    monkeypatch.setattr(endpoints, "chat_vision", fake_chat)
    with pytest.raises(AllOCRDown) as ei:
        endpoints.ocr_with_failover(
            ("http://box1", "http://box2"), "m", "p", [], timeout=1.0
        )
    assert "box1" in str(ei.value) and "box2" in str(ei.value)


def test_image64_non_decodable_bytes_still_encodes():
    # Garbage bytes must not raise — they fall back to raw base64.
    img = Image64.from_bytes(b"not-an-image", max_edge=512)
    assert img.data_url.startswith("data:image/")
