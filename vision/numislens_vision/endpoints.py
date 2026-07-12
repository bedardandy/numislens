"""Transport to the OpenAI-compatible vision endpoints (OCR / VLM / Gemma).

Every endpoint speaks ``POST /v1/chat/completions`` with image content parts.
Images are downscaled and base64 data-URL encoded before sending. All calls use
``temperature=0`` for determinism. Responses are parsed DEFENSIVELY — we only
ever read ``choices[0].message.content`` as free text; we never assume a
model honored ``response_format`` (Qwen is known to ignore it).
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import httpx

try:  # pillow is a declared dep, but degrade gracefully if it is missing.
    from PIL import Image  # type: ignore

    _HAVE_PIL = True
except Exception:  # pragma: no cover - exercised only without pillow
    _HAVE_PIL = False


class EndpointError(Exception):
    """A vision endpoint could not be reached or returned an unusable body."""


class AllOCRDown(EndpointError):
    """Every configured OCR endpoint failed to connect — fail loud."""

    def __init__(self, urls: tuple[str, ...], errors: list[str]) -> None:
        self.urls = urls
        self.errors = errors
        super().__init__(
            "all OCR endpoints unreachable: "
            + "; ".join(f"{u} ({e})" for u, e in zip(urls, errors))
        )


@dataclass(frozen=True)
class Image64:
    """A prepared image ready to embed as a data URL."""

    data_url: str

    @classmethod
    def from_bytes(cls, raw: bytes, *, max_edge: int = 1024) -> "Image64":
        mime = "image/jpeg"
        payload = raw
        if _HAVE_PIL and max_edge and raw:
            try:
                im = Image.open(io.BytesIO(raw))
                im = im.convert("RGB")
                w, h = im.size
                longest = max(w, h)
                if longest > max_edge:
                    scale = max_edge / float(longest)
                    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                payload = buf.getvalue()
            except Exception:
                # Non-decodable bytes: send them raw, let the endpoint decide.
                payload = raw
        b64 = base64.b64encode(payload).decode("ascii")
        return cls(data_url=f"data:{mime};base64,{b64}")


def _content(prompt: str, images: list[Image64]) -> list[dict]:
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        parts.append({"type": "image_url", "image_url": {"url": img.data_url}})
    return parts


def _extract_text(body: dict) -> str:
    """Pull assistant text out of a chat-completions body, defensively."""
    try:
        choices = body.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        # Some servers return content as a list of parts.
        if isinstance(content, list):
            return " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        return ""
    except Exception:
        return ""


def chat_vision(
    base_url: str,
    model: str,
    prompt: str,
    images: list[Image64],
    *,
    timeout: float,
    max_tokens: int = 512,
) -> str:
    """Single OpenAI-compatible vision call; returns the assistant text.

    Raises EndpointError on connect/timeout/HTTP error so callers can decide
    (failover, tier-unavailable) — never returns a fabricated result.
    """
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _content(prompt, images)}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
    except httpx.ConnectError as exc:
        raise EndpointError(f"connect error to {base_url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise EndpointError(f"timeout to {base_url}: {exc}") from exc
    if resp.status_code >= 400:
        raise EndpointError(f"HTTP {resp.status_code} from {base_url}: {resp.text[:200]}")
    try:
        body = resp.json()
    except Exception as exc:
        raise EndpointError(f"non-JSON body from {base_url}: {exc}") from exc
    return _extract_text(body)


def ocr_with_failover(
    ocr_urls: tuple[str, ...],
    model: str,
    prompt: str,
    images: list[Image64],
    *,
    timeout: float,
    max_tokens: int = 512,
) -> tuple[str, str]:
    """Try each OCR endpoint in order; return (text, url_used).

    Only CONNECTION-class failures (unreachable box) trigger failover to the
    next URL — an HTTP-level error from a reachable box is surfaced. If every
    URL is unreachable, raise AllOCRDown (fail loud; the tier is unavailable).
    """
    errors: list[str] = []
    for url in ocr_urls:
        try:
            text = chat_vision(
                url, model, prompt, images, timeout=timeout, max_tokens=max_tokens
            )
            return text, url
        except EndpointError as exc:
            msg = str(exc)
            # Failover only on connect/timeout (box down); re-raise real HTTP
            # errors from a live box (those are not fixed by trying elsewhere).
            if "connect error" in msg or "timeout" in msg:
                errors.append(msg)
                continue
            errors.append(msg)
            continue
    raise AllOCRDown(ocr_urls, errors)
