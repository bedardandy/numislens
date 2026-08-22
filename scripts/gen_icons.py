#!/usr/bin/env python3
"""Regenerate public/icons/icon-<N>x<N>.png from public/icons/icon.svg.

The SVG is geometrically simple (a lens/clock face): a light disc with a blue
ring, two stroked hands, and a blue hub dot. Pillow cannot rasterize SVG
directly and macOS lacks rsvg/cairo by default, so this script REDRAWS the
same geometry at high resolution and downsamples with LANCZOS — visually
equivalent output, no native SVG dependency.

Usage: .venv/bin/python scripts/gen_icons.py   (requires pillow)

If you edit icon.svg's geometry, mirror the change here and re-run.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = REPO_ROOT / "public" / "icons"

# viewBox 0 0 24 24 palette/geometry from icon.svg.
BLUE = ((33,) * 0 + (33, 150, 243))  # #2196f3
BG = (245, 245, 245)  # #f5f5f5
SS = 64  # supersample canvas edge: viewBox units * SS
SIZES = (72, 96, 128, 144, 152, 192, 384, 512)


def render_supersampled() -> Image.Image:
    img = Image.new("RGBA", (SS * 24, SS * 24), (0, 0, 0, 0))

    def u(v: float) -> float:
        return v * SS

    d = ImageDraw.Draw(img)
    ring_w = u(2)
    r = u(10)
    cx = cy = u(12)
    d.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(*BG, 255),
        outline=(*BLUE, 255),
        width=max(1, round(ring_w)),
    )
    # Hands: M12 6 v6 l4 2  (stroke-width 2, round caps/joins).
    pts = [(u(12), u(6)), (u(12), u(12)), (u(16), u(14))]
    w = max(1, round(u(2)))
    d.line(pts, fill=(*BLUE, 255), width=w, joint="curve")
    for px, py in (pts[0], pts[-1]):  # round caps
        rr = w / 2
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(*BLUE, 255))
    # Hub dot: r=2 filled blue.
    hr = u(2)
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(*BLUE, 255))
    return img


def main() -> int:
    src = render_supersampled()
    for size in SIZES:
        out = ICONS_DIR / f"icon-{size}x{size}.png"
        src.resize((size, size), Image.LANCZOS).save(out, format="PNG")
        print(f"wrote {out.relative_to(REPO_ROOT)} ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
