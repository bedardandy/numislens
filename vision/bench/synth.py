"""Render a crude synthetic 'coin' image (circle + stamped text).

For harness liveness only — a drawn disc with legend/date/mintmark text. NOT a
real coin and NEVER a source of accuracy numbers; it exists to prove transport,
parsing, and the gate are wired end to end.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def render_coin_face(lines: list[str], size: int = 512) -> bytes:
    """Draw a light disc on dark ground with the given text lines; JPEG bytes."""
    img = Image.new("RGB", (size, size), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    margin = size // 12
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(200, 180, 120),
        outline=(120, 100, 60),
        width=6,
    )
    n = len(lines)
    fs = max(28, size // 10)
    font = _font(fs)
    total_h = n * (fs + 10)
    y = (size - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((size - w) // 2, y), line, fill=(30, 25, 10), font=font)
        y += fs + 10
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def synthetic_pair(year: int = 1943, mintmark: str = "D") -> tuple[bytes, bytes]:
    """A synthetic obverse/reverse pair for the given year+mintmark."""
    obverse = render_coin_face(["LIBERTY", str(year), mintmark])
    reverse = render_coin_face(["UNITED STATES", "ONE CENT"])
    return obverse, reverse
