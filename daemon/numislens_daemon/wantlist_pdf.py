"""Want-list PDF rendering (pure module, no FastAPI).

Renders the dict from ``numislens_core.needs`` to a compact, printable checklist
a collector takes coin shopping: the set name, completion stats, and every
missing slot as a checkbox line laid out in columns, with key dates bolded and
starred. Mirrors the conventions in ``report_pdf.py`` (FPDF, US Letter, mm,
Helvetica core font -> latin-1, so no fancy glyphs). A complete set renders a
valid one-line "Set complete" PDF.
"""

from __future__ import annotations

from fpdf import FPDF

LINE_H = 5.5
MARGIN = 15.0

# fpdf core fonts encode as latin-1; avoid non-latin glyphs.
_ELLIPSIS = "..."


def _fit(pdf: FPDF, text: str, width: float, pad: float = 1.0) -> str:
    """Truncate text with an ellipsis so it never overflows its column."""
    text = str(text)
    if pdf.get_string_width(text) <= width - pad:
        return text
    while text and pdf.get_string_width(text + _ELLIPSIS) > width - pad:
        text = text[:-1]
    return text + _ELLIPSIS if text else ""


def _content_width(pdf: FPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _slot_label(slot: dict) -> str:
    """'1914-D' or '1909-S VDB' from a missing-slot dict."""
    label = f"{slot['year']}-{slot['mint']}"
    note = slot.get("note")
    if note:
        label += f" {note}"
    return label


def render_wantlist_pdf(needs: dict) -> bytes:
    """Render a set's want-list dict (from ``numislens_core.needs``) to PDF bytes."""
    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(True, margin=MARGIN)
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.add_page()
    full = _content_width(pdf)

    # --- title + stats -----------------------------------------------------
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, _fit(pdf, f"Want List: {needs['name']}", full), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    filled = needs["filled"]
    total = needs["total_slots"]
    pct = needs["completion_pct"]
    missing = needs.get("missing") or []
    pdf.cell(
        0,
        LINE_H,
        f"Filled {filled} of {total}  ({pct}% complete)",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    key_missing = needs.get("key_dates_missing", 0)
    pdf.cell(
        0,
        LINE_H,
        f"Still needed: {len(missing)}"
        + (f"  (including {key_missing} key date(s))" if key_missing else ""),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # --- complete set: a valid, honest one-liner ---------------------------
    if not missing:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, LINE_H * 2, "Set complete - nothing left to hunt.", new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    # --- missing slots, flowed into columns (key dates bold + starred) -----
    cols = 3
    col_w = full / cols
    top = pdf.get_y()
    bottom = pdf.h - pdf.b_margin
    col = 0
    y = top
    for slot in missing:
        if y + LINE_H > bottom:
            col += 1
            y = top
            if col >= cols:
                pdf.add_page()
                top = pdf.get_y()
                y = top
                col = 0
        x = pdf.l_margin + col * col_w
        pdf.set_xy(x, y)
        label = _slot_label(slot)
        if slot.get("key_date"):
            pdf.set_font("Helvetica", "B", 9)
            line = f"[ ] {label}  (KEY DATE) *"
        else:
            pdf.set_font("Helvetica", "", 9)
            line = f"[ ] {label}"
        pdf.cell(col_w, LINE_H, _fit(pdf, line, col_w))
        y += LINE_H

    # --- footer ------------------------------------------------------------
    pdf.set_y(bottom - LINE_H)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(
        0,
        LINE_H,
        f"NumisLens want list - {needs['set_key']} - key dates starred (*)",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return bytes(pdf.output())
