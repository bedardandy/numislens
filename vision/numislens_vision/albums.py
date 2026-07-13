"""Album / coin-folder page analysis: OCR the labels, judge each slot.

Mirrors the tiers.py / pipeline.py conventions: every model call goes through
``endpoints`` (so tests monkeypatch HTTP and it runs with no live endpoints), and
NOTHING a model returns is trusted as-is. The honesty rule is paramount here --
the labels are READ (never inferred from coin designs), and any dark/ambiguous
hole is 'uncertain', never guessed filled or empty.

Flow per page:

1. A cheap VLM page-classifier: "is this a coin-folder page with labeled slots?"
   -> ``not_a_page`` short-circuits (no slots).
2. T1 OCR (Paddle): transcribe the page title + each printed slot label.
3. T2 VLM: shown the image + the OCR label list, return filled/empty/unclear per
   label AND echo the label. Echo must match the OCR text after canon, else that
   slot -> 'uncertain'. 'unclear' -> 'uncertain'.
4. Optional Gemma cross-vote: any disagreement -> 'uncertain'.

``analyze_import`` pulls the import + page images from the daemon, analyzes every
un-analyzed page, and POSTs each analysis back. Year/mint parsing is the daemon's
job (see numislens_core.albums.parse_slot_label) -- this module only reads text.

CLI: ``python -m numislens_vision.albums <import_id>``.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from dataclasses import dataclass, field

import httpx

from . import endpoints
from .config import VisionConfig, load_config
from .endpoints import Image64

# --- Prompts ---------------------------------------------------------------

PAGE_CLASSIFY_PROMPT = (
    "Look at this image. Is it a page from a coin folder or coin album -- a board "
    "with labeled holes/slots for individual coins, each slot printed with a year "
    "and mint mark? Answer only 'yes' or 'no'."
)

ALBUM_OCR_PROMPT = (
    "This is a page from a coin folder. Transcribe the printed text exactly as "
    "printed. First the page title/heading, then the small printed label under "
    "each coin slot (a year and sometimes a mint letter), one label per line. "
    "Read only the printed text; do NOT describe or interpret the coins."
)

FILL_PROMPT_TEMPLATE = (
    "This is a page from a coin folder. Each printed label marks a slot that "
    "either holds a coin or is an empty hole. For EACH label listed below, decide "
    "if that slot is FILLED (a coin is clearly seated in the hole) or EMPTY (you "
    "can see the bare board/hole), or UNCLEAR if glare, shadow, or a dark toned "
    "coin makes it ambiguous. Do NOT guess -- when in any doubt, answer unclear. "
    "Do not read the year off the coin; judge only presence. Echo each label "
    "exactly as given.\n"
    "Reply with one line per label in the form:\n"
    "<label> => <filled|empty|unclear>\n\n"
    "Labels:\n{labels}"
)

# A slot judgement below this confidence is downgraded to 'uncertain'.
CONFIDENCE_THRESHOLD = 0.5
_CONF_AGREE = 0.9
_CONF_UNCERTAIN = 0.4

_YEAR_RE = re.compile(r"(1[5-9]\d\d|20\d\d)")


@dataclass
class PageReading:
    page_type: str  # 'page' | 'not_a_page'
    page_title: str | None = None
    slots: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# small local canonicalizers (vision must not import numislens_core)
# ---------------------------------------------------------------------------

def _canon_label(text: str | None) -> str:
    """Collapse a label to alphanumerics for echo-matching ('1943 D.'->'1943d')."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _canon_state(text: str | None) -> str | None:
    """Map free fill-state text to filled/empty/unclear, or None if unreadable."""
    if not text:
        return None
    low = text.lower()
    if re.search(r"\b(unclear|unsure|ambig\w*|cannot tell|can't tell|unknown)\b", low):
        return "unclear"
    if re.search(r"\b(empty|bare|no coin|vacant|missing|hole)\b", low):
        return "empty"
    if re.search(r"\b(filled|full|present|occupied|has a coin|a coin)\b", low):
        return "filled"
    return None


def _is_page(text: str | None) -> bool:
    """A classifier answer is 'page' unless it clearly says no."""
    if not text:
        return True
    low = text.lower()
    if re.search(r"\byes\b", low):
        return True
    if re.search(r"\bno\b", low) or re.search(r"\bnot\b", low):
        return False
    return True


# ---------------------------------------------------------------------------
# OCR parsing
# ---------------------------------------------------------------------------

def _parse_ocr(text: str) -> tuple[str | None, list[str]]:
    """Split OCR text into (page_title, [slot label strings]).

    A line with two+ year tokens is a title (a year-range heading); a line with
    exactly one year token is a slot label. The first title line wins.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title: str | None = None
    labels: list[str] = []
    for ln in lines:
        years = _YEAR_RE.findall(ln)
        if len(years) >= 2 and title is None:
            title = ln
        elif len(years) == 1:
            labels.append(ln)
        elif title is None and not years:
            # A leading heading with no year at all (e.g. "LINCOLN CENTS").
            title = ln
    return title, labels


# ---------------------------------------------------------------------------
# fill judgement
# ---------------------------------------------------------------------------

def _parse_fill_response(text: str) -> dict[str, tuple[str, str]]:
    """Parse '<label> => <state>' lines into {canon_label: (echo, state)}."""
    out: dict[str, tuple[str, str]] = {}
    for line in (text or "").splitlines():
        if "=>" in line:
            left, right = line.split("=>", 1)
        elif "|" in line:
            left, right = line.split("|", 1)
        elif ":" in line:
            left, right = line.rsplit(":", 1)
        else:
            continue
        echo = left.strip()
        state = _canon_state(right)
        if echo and state:
            out[_canon_label(echo)] = (echo, state)
    return out


def _judge_slots(
    labels: list[str],
    vlm_map: dict[str, tuple[str, str]],
    gemma_map: dict[str, tuple[str, str]] | None,
) -> list[dict]:
    """Combine the VLM (and optional Gemma) fill votes into per-slot readings.

    Honesty gate: a label the VLM did not echo (or echoed with a mismatched
    text), an 'unclear' vote, or a Gemma disagreement all collapse to
    'uncertain'. Only a clean filled/empty with (if present) Gemma concurrence
    is trusted.
    """
    slots: list[dict] = []
    for i, label in enumerate(labels):
        key = _canon_label(label)
        entry = vlm_map.get(key)
        if entry is None:
            state = "uncertain"  # echo missing/mismatched
        else:
            _echo, vstate = entry
            state = "uncertain" if vstate == "unclear" else vstate

        if gemma_map is not None and state in ("filled", "empty"):
            g_entry = gemma_map.get(key)
            if g_entry is None or g_entry[1] != state:
                state = "uncertain"  # third voter disagreed or abstained

        slots.append(
            {
                "slot_index": i,
                "label_text": label,
                "fill_state": state,
                "confidence": _CONF_AGREE if state in ("filled", "empty") else _CONF_UNCERTAIN,
            }
        )
    return slots


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def analyze_page(cfg: VisionConfig, image_b64: str) -> PageReading:
    """Analyze one album page image (base64 string). Returns a PageReading."""
    images = [Image64(data_url=f"data:image/jpeg;base64,{image_b64}")]

    # 1. Cheap page classifier -- short-circuit non-pages.
    try:
        cls = endpoints.chat_vision(
            cfg.vlm_url, cfg.vlm_model, PAGE_CLASSIFY_PROMPT, images,
            timeout=cfg.vlm_timeout,
        )
    except endpoints.EndpointError:
        cls = None
    if cls is not None and not _is_page(cls):
        return PageReading(page_type="not_a_page", page_title=None, slots=[])

    # 2. OCR the title + labels.
    try:
        ocr_text, _url = endpoints.ocr_with_failover(
            cfg.ocr_urls, cfg.ocr_model, ALBUM_OCR_PROMPT, images, timeout=cfg.ocr_timeout
        )
    except endpoints.EndpointError:
        # No OCR -> no labels to judge; report an empty page reading honestly.
        return PageReading(page_type="page", page_title=None, slots=[])

    page_title, labels = _parse_ocr(ocr_text)
    if not labels:
        return PageReading(page_type="page", page_title=page_title, slots=[])

    # 3. VLM fill judgement over the OCR labels.
    prompt = FILL_PROMPT_TEMPLATE.format(labels="\n".join(labels))
    try:
        vlm_text = endpoints.chat_vision(
            cfg.vlm_url, cfg.vlm_model, prompt, images, timeout=cfg.vlm_timeout
        )
        vlm_map = _parse_fill_response(vlm_text)
    except endpoints.EndpointError:
        vlm_map = {}

    # 4. Optional Gemma cross-vote (never fatal when absent/down).
    gemma_map: dict[str, tuple[str, str]] | None = None
    if cfg.gemma_url:
        try:
            gemma_text = endpoints.chat_vision(
                cfg.gemma_url, cfg.gemma_model, prompt, images, timeout=cfg.gemma_timeout
            )
            gemma_map = _parse_fill_response(gemma_text)
        except endpoints.EndpointError:
            gemma_map = None

    slots = _judge_slots(labels, vlm_map, gemma_map)
    return PageReading(page_type="page", page_title=page_title, slots=slots)


class AlbumDaemonError(Exception):
    pass


class _AlbumClient:
    """Minimal REST client for the daemon album endpoints (mirrors DaemonClient).

    Kept local to this module so daemon_client.py is untouched. Only the three
    calls analyze_import needs.
    """

    def __init__(self, cfg: VisionConfig) -> None:
        self._base = cfg.daemon_url
        self._headers = {"Authorization": f"Bearer {cfg.token}"}
        self._timeout = 30.0

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base, headers=self._headers, timeout=self._timeout
        )

    def get_import(self, import_id: int) -> dict:
        with self._client() as c:
            resp = c.get(f"/api/v1/albums/imports/{import_id}")
        if resp.status_code >= 400:
            raise AlbumDaemonError(f"API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def get_page_image(self, import_id: int, page_id: int) -> bytes:
        with self._client() as c:
            resp = c.get(f"/api/v1/albums/imports/{import_id}/pages/{page_id}/image")
        if resp.status_code >= 400:
            raise AlbumDaemonError(f"API error {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def post_analysis(self, import_id: int, page_id: int, body: dict) -> dict:
        with self._client() as c:
            resp = c.post(
                f"/api/v1/albums/imports/{import_id}/pages/{page_id}/analysis",
                json=body,
            )
        if resp.status_code >= 400:
            raise AlbumDaemonError(f"API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()


def analyze_import(cfg: VisionConfig, import_id: int, client=None) -> list[dict]:
    """Analyze every un-analyzed page of an import and POST each result back.

    Returns a per-page summary. Vision NEVER commits -- a human reviews and
    commits via the daemon.
    """
    client = client or _AlbumClient(cfg)
    state = client.get_import(import_id)
    results: list[dict] = []
    for page in state.get("pages", []):
        if page.get("analyzed_at"):
            continue  # already analyzed; leave human/earlier work untouched
        raw = client.get_page_image(import_id, page["page_id"])
        image_b64 = base64.b64encode(raw).decode("ascii")
        reading = analyze_page(cfg, image_b64)
        body = {
            "page_title": reading.page_title,
            "page_type": reading.page_type,
            "slots": reading.slots,
        }
        client.post_analysis(import_id, page["page_id"], body)
        results.append(
            {
                "page_id": page["page_id"],
                "page_type": reading.page_type,
                "slot_count": len(reading.slots),
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m numislens_vision.albums <import_id>", file=sys.stderr)
        return 2
    try:
        import_id = int(argv[0])
    except ValueError:
        print(f"error: import_id must be an integer, got {argv[0]!r}", file=sys.stderr)
        return 2
    cfg = load_config()
    try:
        results = analyze_import(cfg, import_id)
    except Exception as exc:  # fail loud
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
