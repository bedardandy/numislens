"""Appraisal-report PDF rendering (pure module, no FastAPI).

Renders the dict from ``numislens_core.build_appraisal_report`` to a US Letter
portrait PDF. The platform's NO-FABRICATION rule carries through here: unvalued
coins are disclosed by count only and NEVER printed with a made-up value.
"""

from __future__ import annotations

from fpdf import FPDF

from .serializers import dollars

# All spatial units are millimetres (FPDF unit="mm").
LINE_H = 5.0
MARGIN = 15.0

# fpdf core fonts encode as latin-1, so avoid the U+2026 ellipsis glyph.
_ELLIPSIS = "..."


def _money(cents: int | None) -> str:
    """dollars() but never None -- an absent figure renders as an em dash."""
    out = dollars(cents)
    return out if out is not None else "--"


def _signed(cents: int) -> str:
    """Signed money for gain/loss: leading + or - outside the dollar sign."""
    sign = "+" if cents >= 0 else "-"
    return f"{sign}{dollars(abs(cents))}"


def _series_label(row: dict) -> str:
    """'<series> <year>-<mintmark>' from a highlight row, omitting blanks."""
    parts: list[str] = []
    if row.get("series"):
        parts.append(str(row["series"]))
    ym = ""
    if row.get("year"):
        ym = str(row["year"])
    if row.get("mintmark"):
        ym += "-" + str(row["mintmark"])
    if ym:
        parts.append(ym)
    return " ".join(parts) if parts else "(unattributed)"


def _fit(pdf: FPDF, text: str, width: float, pad: float = 1.0) -> str:
    """Truncate text with an ellipsis so it never overflows its column."""
    text = str(text)
    if pdf.get_string_width(text) <= width - pad:
        return text
    while text and pdf.get_string_width(text + _ELLIPSIS) > width - pad:
        text = text[:-1]
    return text + _ELLIPSIS if text else ""


def _check_break(pdf: FPDF, needed: float) -> None:
    """Manual page break so multi-row tables never straddle the bottom margin."""
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()


def _heading(pdf: FPDF, text: str) -> None:
    _check_break(pdf, LINE_H * 2)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, LINE_H, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)


def _kv(pdf: FPDF, label: str, value: str) -> None:
    _check_break(pdf, LINE_H)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(55, LINE_H, label)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, LINE_H, value, new_x="LMARGIN", new_y="NEXT")


def _table(
    pdf: FPDF,
    headers: list[str],
    widths: list[float],
    rows: list[list[str]],
    aligns: list[str] | None = None,
) -> None:
    """Draw a simple bordered-header table; cells truncate to their width."""
    aligns = aligns or ["L"] * len(headers)
    _check_break(pdf, LINE_H * 2)
    pdf.set_font("Helvetica", "B", 8)
    for text, width, align in zip(headers, widths, aligns):
        pdf.cell(width, LINE_H, _fit(pdf, text, width), border="B", align=align)
    pdf.ln(LINE_H)
    pdf.set_font("Helvetica", "", 8)
    for row in rows:
        _check_break(pdf, LINE_H)
        for text, width, align in zip(row, widths, aligns):
            pdf.cell(width, LINE_H, _fit(pdf, text, width), align=align)
        pdf.ln(LINE_H)


def _content_width(pdf: FPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def render_appraisal_pdf(report: dict) -> bytes:
    """Render an appraisal report dict to PDF bytes (valid even when empty)."""
    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(True, margin=MARGIN)
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.add_page()
    full = _content_width(pdf)

    # --- Title + provenance ------------------------------------------------
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "NumisLens Appraisal Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, LINE_H, f"Generated: {report['generated_at']}", new_x="LMARGIN", new_y="NEXT")

    spot = report.get("spot") or {}
    _heading(pdf, "Spot Prices")
    if spot:
        for metal in sorted(spot):
            s = spot[metal]
            line = (
                f"{metal}: {_money(s['price_usd_cents'])}/ozt  "
                f"source {s['source']}  fetched {s['fetched_at']}"
            )
            _check_break(pdf, LINE_H)
            pdf.cell(0, LINE_H, _fit(pdf, line, full), new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, LINE_H, "No primary-source spot prices available.", new_x="LMARGIN", new_y="NEXT")

    # --- Totals ------------------------------------------------------------
    totals = report["totals"]
    _heading(pdf, "Totals")
    _kv(pdf, "Best total value", _money(totals["best_total_cents"]))
    _kv(pdf, "Coins valued", f"{totals['valued_count']} of {totals['coin_count']}")
    _kv(pdf, "Collectible component", _money(totals["collectible_total_cents"]))
    _kv(pdf, "Melt component", _money(totals["melt_total_cents"]))
    _kv(pdf, "Face component", _money(totals["face_total_cents"]))
    # Cost basis / gain-loss only meaningful when some coin carries a basis.
    if totals["cost_basis_count"] > 0:
        _kv(
            pdf,
            "Cost basis",
            f"{_money(totals['cost_basis_total_cents'])} over {totals['cost_basis_count']} coins",
        )
        _kv(
            pdf,
            "Gain / loss (paired)",
            f"{_signed(totals['gain_loss_cents'])} "
            f"({_money(totals['paired_best_cents'])} vs {_money(totals['paired_cost_cents'])})",
        )
    # Grand total folds in roll value; only shown when rolls contribute value.
    if totals.get("roll_best_total_cents"):
        _kv(pdf, "Roll best total", _money(totals["roll_best_total_cents"]))
        _kv(pdf, "Grand total (coins + rolls)", _money(totals["grand_total_cents"]))

    # --- Breakdown ---------------------------------------------------------
    bd = report["breakdown"]
    _heading(pdf, "Breakdown by Winning Basis")
    bd_rows = [
        ["Collectible", str(bd["collectible"]["count"]), _money(bd["collectible"]["total_cents"])],
        ["Melt", str(bd["melt"]["count"]), _money(bd["melt"]["total_cents"])],
        ["Face value", str(bd["face"]["count"]), _money(bd["face"]["total_cents"])],
    ]
    if bd["unvalued"]["count"] > 0:
        # Unvalued coins have no basis for value -- count only, never a figure.
        bd_rows.append(
            [
                "Unvalued",
                str(bd["unvalued"]["count"]),
                "no basis for value -- excluded from totals",
            ]
        )
    _table(
        pdf,
        ["Basis", "Count", "Total"],
        [full * 0.55, full * 0.15, full * 0.30],
        bd_rows,
        aligns=["L", "R", "R"],
    )

    # --- Highlights --------------------------------------------------------
    highlights = report.get("highlights") or []
    _heading(pdf, f"Top {report['top_n']} Highlights")
    if highlights:
        rows = []
        for rank, h in enumerate(highlights, start=1):
            rows.append(
                [
                    str(rank),
                    str(h["accession_no"]),
                    _series_label(h),
                    str(h.get("grade_bucket") or "--"),
                    str(h["best_basis"]),
                    _money(h["best_cents"]),
                    _money(h["melt_cents"]) if h["melt_cents"] is not None else "--",
                    _money(h["collectible_cents"]) if h["collectible_cents"] is not None else "--",
                ]
            )
        _table(
            pdf,
            ["#", "Accession", "Series / Year", "Grade", "Basis", "Value", "Melt", "Collect."],
            [
                full * 0.05,
                full * 0.16,
                full * 0.25,
                full * 0.09,
                full * 0.11,
                full * 0.12,
                full * 0.11,
                full * 0.11,
            ],
            rows,
            aligns=["R", "L", "L", "L", "L", "R", "R", "R"],
        )
    else:
        pdf.cell(0, LINE_H, "No valued coins to highlight.", new_x="LMARGIN", new_y="NEXT")

    # --- Groups (each section skipped entirely when empty) -----------------
    groups = report.get("groups") or {}

    sets_ = groups.get("sets") or []
    if sets_:
        _heading(pdf, "Sets")
        _table(
            pdf,
            ["Set", "Filled / Slots", "Value"],
            [full * 0.55, full * 0.20, full * 0.25],
            [
                [str(g["name"]), f"{g['filled']} / {g['total_slots']}", _money(g["value_cents"])]
                for g in sets_
            ],
            aligns=["L", "R", "R"],
        )

    mints = groups.get("mints") or []
    if mints:
        _heading(pdf, "Mints")
        _table(
            pdf,
            ["Mintmark", "Count", "Value"],
            [full * 0.55, full * 0.20, full * 0.25],
            [[str(g["mintmark"]), str(g["count"]), _money(g["value_cents"])] for g in mints],
            aligns=["L", "R", "R"],
        )

    series = groups.get("series") or []
    if series:
        _heading(pdf, "Series")
        _table(
            pdf,
            ["Series", "Count", "Value"],
            [full * 0.55, full * 0.20, full * 0.25],
            [[str(g["series"]), str(g["count"]), _money(g["value_cents"])] for g in series],
            aligns=["L", "R", "R"],
        )

    metals = groups.get("metals") or []
    if metals:
        _heading(pdf, "Metals")
        _table(
            pdf,
            ["Metal", "Count", "Melt", "Value"],
            [full * 0.40, full * 0.20, full * 0.20, full * 0.20],
            [
                [str(g["metal"]), str(g["count"]), _money(g["melt_cents"]), _money(g["value_cents"])]
                for g in metals
            ],
            aligns=["L", "R", "R", "R"],
        )

    rolls_ = groups.get("rolls") or []
    if rolls_:
        _heading(pdf, "Rolls")
        _table(
            pdf,
            ["Roll", "Denomination", "Count", "Status", "Basis", "Value"],
            [
                full * 0.18,
                full * 0.27,
                full * 0.11,
                full * 0.16,
                full * 0.12,
                full * 0.16,
            ],
            [
                [
                    str(g["roll_no"]),
                    str(g["denomination"]),
                    str(g["count"]),
                    str(g["status"]),
                    str(g["basis"]),
                    _money(g["value_cents"]),
                ]
                for g in rolls_
            ],
            aligns=["L", "L", "R", "L", "L", "R"],
        )

    # --- Data-quality footer (only nonzero disclosures) --------------------
    dq = report.get("data_quality") or {}
    notes: list[str] = []
    if dq.get("unvalued_count"):
        notes.append(f"{dq['unvalued_count']} coin(s) unvalued (excluded from totals)")
    if dq.get("stale_count"):
        notes.append(f"{dq['stale_count']} coin(s) with stale valuation")
    if dq.get("basis_unspecified_count"):
        notes.append(f"{dq['basis_unspecified_count']} estimate(s) with unspecified basis")
    if dq.get("rolls_unvalued_count"):
        notes.append(f"{dq['rolls_unvalued_count']} roll(s) unvalued (excluded from totals)")
    missing = dq.get("metals_missing_spot") or []
    if missing:
        notes.append("no primary spot for: " + ", ".join(missing))
    if notes:
        _heading(pdf, "Data Quality")
        pdf.set_font("Helvetica", "", 8)
        for note in notes:
            _check_break(pdf, LINE_H)
            pdf.cell(0, LINE_H, _fit(pdf, "- " + note, full), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
