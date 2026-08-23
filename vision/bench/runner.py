#!/usr/bin/env python3
"""Score the tiered pipeline against a staged ground-truth set.

Runs each image pair through T1 (OCR), T2 (VLM), optional T3 (Gemma) and the
agreement gate, then scores per-tier and post-gate accuracy with DATE and
MINTMARK scored separately and strictly (exact match). Daemon-free: it reads
image files (or renders the one synthetic smoke entry) and talks only to the
OCR/VLM endpoints. Synthetic entries are run to prove liveness but EXCLUDED from
every accuracy number.

Usage (from vision/, venv active):
    python bench/runner.py [path/to/ground_truth.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow `import synth`

from numislens_vision import pipeline  # noqa: E402
from numislens_vision.config import load_config  # noqa: E402
from numislens_vision.endpoints import Image64  # noqa: E402

import synth  # noqa: E402

_UNREAD = object()


def _load_pair(base: Path, entry: dict, cfg) -> list[Image64]:
    truth = entry.get("truth", {})
    if entry.get("obverse") == "synthetic" or entry.get("synthetic"):
        obv, rev = synth.synthetic_pair(
            year=truth.get("year") or 1943, mintmark=truth.get("mintmark") or "D"
        )
        raws = [obv, rev]
    else:
        raws = []
        for side in ("obverse", "reverse"):
            p = entry.get(side)
            if not p:
                continue
            path = base / p
            if not path.is_file():
                # A staging mistake, not a pipeline result: raise with enough
                # context to fix the ground-truth entry (the score loop turns
                # this into a per-entry error and keeps scoring the rest).
                raise FileNotFoundError(
                    f"entry {entry.get('id')!r}: image not found: {path}"
                )
            raws.append(path.read_bytes())
    return [Image64.from_bytes(r, max_edge=cfg.max_image_edge) for r in raws]


def _reduce_mint(reading) -> object:
    if reading is None or not getattr(reading, "available", False):
        return _UNREAD
    if reading.mintmark_present is True and reading.mintmark_letter:
        return reading.mintmark_letter
    if reading.mintmark_present is False:
        return None  # affirmatively no mark
    return _UNREAD


class Tally:
    def __init__(self) -> None:
        self.counts: dict[str, list[int]] = {}

    def add(self, key: str, correct: bool) -> None:
        c = self.counts.setdefault(key, [0, 0])
        c[0] += int(bool(correct))
        c[1] += 1

    def pct(self, key: str) -> str:
        c, n = self.counts.get(key, [0, 0])
        return f"{c}/{n} ({100.0 * c / n:.0f}%)" if n else "n/a"


def score(cfg, gt_path: Path) -> dict:
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    base = gt_path.parent
    pairs = data.get("image_pairs", [])
    known_series = sorted(
        {p["truth"]["series"] for p in pairs if p.get("truth", {}).get("series")}
    )

    tally = Tally()
    escalated = 0
    scored = 0
    per_pair: list[dict] = []
    errors: list[str] = []

    for entry in pairs:
        truth = entry.get("truth", {})
        try:
            images = _load_pair(base, entry, cfg)
        except (OSError, ValueError) as exc:
            # Missing/corrupt staged image: record, keep scoring the rest.
            errors.append(str(exc))
            per_pair.append(
                {"id": entry.get("id"), "error": str(exc)}
            )
            continue
        tiered = pipeline.run_tiers_and_gate(
            cfg, images, known_series=known_series, key_date_years=set()
        )
        ocr = tiered["readings"]["ocr"]
        vlm = tiered["readings"]["vlm"]
        accepted = tiered["accepted"]
        esc_fields = {e["field"] for e in tiered["escalations"]}

        rec = {
            "id": entry.get("id"),
            "synthetic": bool(entry.get("synthetic")),
            "accepted": accepted,
            "escalations": sorted(esc_fields),
            "tiers_unavailable": tiered["tiers_unavailable"],
        }
        per_pair.append(rec)

        if entry.get("synthetic"):
            continue  # never scored
        scored += 1
        if esc_fields:
            escalated += 1

        # year (always scored)
        ty = truth.get("year")
        if ty is not None:
            tally.add("ocr.year", ocr.available and ocr.year == ty)
            tally.add("vlm.year", vlm.available and vlm.year == ty)
            tally.add("gate.year", "year" not in esc_fields and accepted["year"] == ty)
        # mintmark (always scored; null truth == expect no mark)
        tm = truth.get("mintmark")  # letter or None (no mark)
        tally.add("ocr.mintmark", _reduce_mint(ocr) == tm)
        tally.add("vlm.mintmark", _reduce_mint(vlm) == tm)
        tally.add(
            "gate.mintmark",
            "mintmark" not in esc_fields and accepted["mintmark"] == tm,
        )
        # series (scored when truth provides it)
        ts = truth.get("series")
        if ts is not None:
            tally.add("vlm.series", vlm.available and vlm.series == ts)
            tally.add("gate.series", accepted["series"] == ts)
        # grade bucket (scored when truth provides it)
        tg = truth.get("grade_bucket")
        if tg is not None:
            tally.add("vlm.grade", vlm.available and vlm.grade_bucket == tg)
            tally.add("gate.grade", accepted["grade_bucket"] == tg)

    esc_rate = f"{escalated}/{scored} ({100.0 * escalated / scored:.0f}%)" if scored else "n/a"
    return {
        "scored_pairs": scored,
        "escalation_rate": esc_rate,
        "staging_errors": errors,
        "per_tier": {k: tally.pct(k) for k in sorted(tally.counts)},
        "per_pair": per_pair,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    gt_path = Path(argv[0]) if argv else Path(__file__).resolve().parent / "ground_truth.json"
    if not gt_path.is_file():
        print(
            f"ground-truth file not found: {gt_path}\n"
            "Copy bench/ground_truth.example.json to bench/ground_truth.json and "
            "stage your coins (see bench/README.md).",
            file=sys.stderr,
        )
        return 2
    cfg = load_config(require_token=False)
    report = score(cfg, gt_path)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    if report["staging_errors"]:
        # The report above is still valid for the entries that ran; exit
        # non-zero so scripts/CI notice the staging problem. Fail loud.
        print(
            f"\n{len(report['staging_errors'])} staging error(s) — fix the "
            "ground-truth entries listed in staging_errors above.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
