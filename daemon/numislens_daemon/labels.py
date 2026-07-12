"""Avery 5160 label-sheet PDF generation (pure module, no FastAPI)."""

from __future__ import annotations

import io

import segno
from fpdf import FPDF

# Fallback only; callers should pass an https base URL so phone cameras can open the QR.
QR_FALLBACK_BASE = "numislens://"

PAGE_W = 8.5
PAGE_H = 11.0
COLS = 3
ROWS = 10
LABEL_W = 2.625
LABEL_H = 1.0
MARGIN_LEFT = 0.1875
MARGIN_TOP = 0.5
COL_PITCH = 2.75
ROW_PITCH = 1.0


def _coin_label_lines(coin: dict) -> tuple[str, str]:
    line1 = coin["accession_no"]
    parts: list[str] = []
    if coin.get("series"):
        parts.append(str(coin["series"]))
    ym = ""
    if coin.get("year"):
        ym = str(coin["year"])
    if coin.get("mintmark"):
        ym += "-" + str(coin["mintmark"])
    if ym:
        parts.append(ym)
    line2 = " ".join(parts)
    return line1, line2


def _qr_png_bytes(data: str) -> io.BytesIO:
    qr = segno.make(data, error="m")
    buff = io.BytesIO()
    qr.save(buff, kind="png", scale=4, border=1)
    buff.seek(0)
    return buff


def page_count(n_coins: int) -> int:
    return max(1, (n_coins + 29) // 30)


def render_labels(coins: list[dict], base_url: str | None = None) -> bytes:
    qr_base = (base_url.rstrip("/") if base_url else QR_FALLBACK_BASE.rstrip("/")) + "/c/"
    pdf = FPDF(orientation="P", unit="in", format="Letter")
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)

    if not coins:
        pdf.add_page()
        return bytes(pdf.output())

    for index, coin in enumerate(coins):
        if index % 30 == 0:
            pdf.add_page()

        pos = index % 30
        row = pos // COLS
        col = pos % COLS
        x = MARGIN_LEFT + col * COL_PITCH
        y = MARGIN_TOP + row * ROW_PITCH

        png = _qr_png_bytes(qr_base + coin["accession_no"])
        qr_size = 0.85
        pdf.image(png, x=x + 0.08, y=y + 0.075, w=qr_size, h=qr_size)

        line1, line2 = _coin_label_lines(coin)
        text_x = x + qr_size + 0.18
        pdf.set_xy(text_x, y + 0.2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(LABEL_W - qr_size - 0.25, 0.2, line1)
        pdf.set_xy(text_x, y + 0.45)
        pdf.set_font("Helvetica", "", 7)
        pdf.multi_cell(LABEL_W - qr_size - 0.25, 0.16, line2)

    return bytes(pdf.output())
