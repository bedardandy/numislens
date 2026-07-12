"""Fail-safe writeback of a gated pipeline result, via the daemon REST API.

Rules (the whole point is that a guessed value never reaches the ledger):

* Accepted identification fields (series/year/mintmark) fill the coin ONLY where
  it is currently NULL — the daemon enforces fill-null-only, so a user/human
  identity is never overwritten; skips are reported.
* An accepted grade bucket is written two ways: onto the coin (fill-null, with
  ``grade_source='local-vlm'`` — grade is always a single-tier VLM read) AND as
  an append-only appraisal record (the provenance trail, low confidence,
  rationale = the tier readings).
* Escalations write NO identification. Instead they append a
  ``vision:escalation`` appraisal note carrying the conflicting readings, then
  mark the coin stale (reason ``vision escalation: <fields>``) via the existing
  digest plumbing so it surfaces in watch/status. No new daemon tables.
"""

from __future__ import annotations

import json

from .config import VisionConfig
from .daemon_client import DaemonClient

# Modest confidence for a photo-grade condition bucket — never presented as a
# firm grade. Kept well under a human/TPG appraisal.
PHOTO_GRADE_CONFIDENCE = 0.5


def _id_tiers(result: dict) -> set[str]:
    tiers: set[str] = set()
    for t in result.get("tiers_used", []):
        head = t.split(":", 1)[0]
        if head in {"ocr", "vlm", "gemma"}:
            tiers.add(head)
    return tiers


def _appraised_by(result: dict) -> str:
    have = _id_tiers(result)
    if "gemma" in have:
        return "vision:cross-vote"
    if {"ocr", "vlm"} <= have:
        return "vision:ocr+vlm"
    return "vision:local-vlm"


def _readings_summary(result: dict) -> str:
    used = ", ".join(result.get("tiers_used", [])) or "none"
    esc = ", ".join(sorted({e["field"] for e in result.get("escalations", [])})) or "none"
    return f"tiers_used=[{used}]; escalated=[{esc}]"


def apply_writeback(
    cfg: VisionConfig, result: dict, client: DaemonClient | None = None
) -> dict:
    """Apply a gated result to the ledger. Returns a per-coin writeback report."""
    client = client or DaemonClient(cfg)
    accession = result["accession"]
    accepted = result.get("accepted", {})
    escalations = result.get("escalations", [])

    report: dict = {
        "accession": accession,
        "written": {},
        "skipped": {},
        "grade_appraisal": None,
        "escalation": None,
    }

    appraised_by = _appraised_by(result)

    # 1. Identification fill-null (series/year/mintmark + grade bucket/source).
    id_fields: dict = {}
    for f in ("series", "year", "mintmark"):
        val = accepted.get(f)
        if val is not None:
            id_fields[f] = val
    if accepted.get("grade_bucket") is not None:
        id_fields["grade_bucket"] = accepted["grade_bucket"]
        id_fields["grade_source"] = "local-vlm"
    if id_fields:
        patched = client.patch_identification(accession, id_fields)
        report["written"] = patched.get("written", {})
        report["skipped"] = patched.get("skipped", {})

    # 2. Grade appraisal trail (append-only). record_appraisal clears staleness,
    #    so it MUST run before the escalation stale-mark below.
    if accepted.get("grade_bucket") is not None:
        client.record_appraisal(
            accession,
            {
                "appraised_by": appraised_by,
                "grade_bucket": accepted["grade_bucket"],
                "confidence": PHOTO_GRADE_CONFIDENCE,
                "rationale": (
                    "photo-grade (VLM T2 condition bucket, not a TPG grade). "
                    + _readings_summary(result)
                ),
            },
        )
        report["grade_appraisal"] = accepted["grade_bucket"]

    # 3. Escalations: note + stale flag (never identification). Runs LAST so the
    #    stale flag survives (record_appraisal above would otherwise clear it).
    if escalations:
        fields = ",".join(sorted({e["field"] for e in escalations}))
        client.record_appraisal(
            accession,
            {
                "appraised_by": "vision:escalation",
                "rationale": (
                    "VISION ESCALATION — conflicting/unresolved readings; do NOT "
                    "auto-resolve, adjudicate with the user or your own vision. "
                    + json.dumps(escalations, ensure_ascii=False)
                ),
            },
        )
        marked = client.mark_stale_digest(
            accession,
            reason=f"vision escalation: {fields}",
            source_note="numislens-vision",
        )
        report["escalation"] = {
            "fields": fields,
            "stale_marked": marked.get("total_marked"),
        }

    return report
