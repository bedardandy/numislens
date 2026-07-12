"""Batch worker: run the pipeline + fail-safe writeback over coins.

Sequential, one coin at a time — the LAN GPUs are shared, no hammering. The
``--pending`` selector is the unattended entrypoint: coins that have images, are
still UNIDENTIFIED (series AND year both null), and carry no prior ``vision:*``
appraisal (so a coin is processed at most once unattended). ``identify`` +
``apply_writeback`` per coin; every result is printed.
"""

from __future__ import annotations

from .config import VisionConfig
from .daemon_client import DaemonClient
from .pipeline import identify
from .writeback import apply_writeback


def _has_vision_appraisal(coin: dict) -> bool:
    return any(
        str(a.get("appraised_by", "")).startswith("vision:")
        for a in coin.get("appraisals", [])
    )


def select_pending(client: DaemonClient) -> list[str]:
    """Accessions eligible for unattended processing.

    UNIDENTIFIED (series and year both null) + has >=1 image + no prior
    vision:* appraisal. Fully-identified coins and already-processed coins are
    skipped so a --pending run is idempotent.
    """
    out: list[str] = []
    for coin in client.list_coins():
        if coin.get("series") is not None or coin.get("year") is not None:
            continue
        full = client.get_coin(coin["accession_no"])
        if not full.get("coin_images"):
            continue
        if _has_vision_appraisal(full):
            continue
        out.append(coin["accession_no"])
    return out


def process(
    cfg: VisionConfig,
    *,
    accession: str | None = None,
    pending: bool = False,
    client: DaemonClient | None = None,
    printer=print,
) -> list[dict]:
    """Process one accession or the whole --pending set. Returns per-coin dicts."""
    client = client or DaemonClient(cfg)
    if bool(accession) == bool(pending):
        raise ValueError("provide exactly one of accession or pending")
    targets = [accession] if accession else select_pending(client)

    if not targets:
        printer("no coins to process (pending set is empty).")
        return []

    out: list[dict] = []
    for acc in targets:
        result = identify(cfg, acc, client=client)
        report = apply_writeback(cfg, result, client=client)
        printer(_format_report(result, report))
        out.append({"result": result, "report": report})
    return out


def status(cfg: VisionConfig, client: DaemonClient | None = None) -> dict:
    """Collection-wide vision status counts (a read; spends nothing)."""
    client = client or DaemonClient(cfg)
    coins = client.list_coins()
    total = len(coins)
    with_images = 0
    vision_processed = 0
    pending = 0
    unidentified = 0
    for coin in coins:
        full = client.get_coin(coin["accession_no"])
        has_img = bool(full.get("coin_images"))
        has_vision = _has_vision_appraisal(full)
        if has_img:
            with_images += 1
        if has_vision:
            vision_processed += 1
        if coin.get("series") is None and coin.get("year") is None:
            unidentified += 1
            if has_img and not has_vision:
                pending += 1
    return {
        "total_coins": total,
        "with_images": with_images,
        "unidentified": unidentified,
        "vision_processed": vision_processed,
        "pending": pending,
    }


def _format_report(result: dict, report: dict) -> str:
    acc = result["accession"]
    accepted = result.get("accepted", {})
    lines = [f"[{acc}]"]
    written = report.get("written") or {}
    skipped = report.get("skipped") or {}
    accepted_str = ", ".join(
        f"{k}={accepted.get(k)}"
        for k in ("series", "year", "mintmark", "grade_bucket")
        if accepted.get(k) is not None
    )
    lines.append("  accepted: " + (accepted_str or "(none)"))
    if written:
        lines.append("  written: " + ", ".join(f"{k}={v}" for k, v in written.items()))
    if skipped:
        lines.append(
            "  skipped (already set, not overwritten): "
            + ", ".join(f"{k}={v}" for k, v in skipped.items())
        )
    if report.get("grade_appraisal"):
        lines.append(f"  grade appraisal recorded: {report['grade_appraisal']} (photo-grade)")
    esc = result.get("escalations", [])
    if esc:
        lines.append(
            "  ESCALATIONS (adjudicate — not written): "
            + "; ".join(f"{e['field']} {e['readings']} ({e['note']})" for e in esc)
        )
        if report.get("escalation"):
            lines.append(f"  -> marked stale: {report['escalation']['fields']}")
    unavailable = result.get("tiers_unavailable", [])
    if unavailable:
        lines.append("  tiers unavailable: " + "; ".join(unavailable))
    return "\n".join(lines)


def format_status(st: dict) -> str:
    return (
        "NumisLens vision status\n"
        f"  total coins:        {st['total_coins']}\n"
        f"  with images:        {st['with_images']}\n"
        f"  unidentified:       {st['unidentified']}\n"
        f"  vision-processed:   {st['vision_processed']}\n"
        f"  pending (--pending):{st['pending']}"
    )
