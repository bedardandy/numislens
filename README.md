# NumisLens

> **Research / experimental alpha.** This is a working personal-scale system published for the curious: APIs, schemas, and UI may change without notice, the vision pipeline's real-world accuracy is unmeasured (the benchmark harness exists, the ground-truth photo set does not yet), and nothing here is a substitute for a professional appraisal. Use on a copy of data you can afford to lose.

NumisLens is a coin-collection platform built around a single SQLite ledger and a small REST daemon, with thin clients (a PWA, a Claude MCP/skill, and more) over one OpenAPI surface. The Progressive Web App (PWA) is a phone/desktop view onto that ledger: browse and add coins, organize physical locations, track set completion and rolls, import coin albums from photos, watch deterministic melt values, print QR labels and want lists, and reconcile boxes offline. Coin identification and grading run through a tiered local-LLM vision pipeline behind agreement gates — values are never fabricated: every figure traces to a real input (an appraisal, a metal weight times a fetched spot price, or face value), and anything unknown is disclosed as unknown.

## Repository layout

- **`core/`** — the collection ledger: a dependency-free Python package (`numislens_core`) over a single SQLite database, plus its data (SQL migrations, the compositions seed, and set manifests in `core/sets/`). This is the source of truth for the whole platform. Run its tests with `cd core && python3 -m pytest`.
- **`daemon/`** — FastAPI REST + OpenAPI surface, bearer auth, label PDFs, and the value-watch staleness endpoints (`/watch/status`, `/watch/digest`).
- **`ops/`** — operational files: user-level systemd units for the daily melt update, plus Litestream and dump-based backup config. See `ops/README.md` and `ops/BACKUP.md`. Nothing here is installed or enabled automatically.
- **`surfaces/`** — thin assistant skins over the REST API: a Claude MCP server (`surfaces/mcp/`) and Claude Code skill (`surfaces/claude/SKILL.md`), a ChatGPT Custom GPT Action (`surfaces/chatgpt/`), a Gemini Gem (`surfaces/gemini/`), and Apple Shortcuts recipes (`surfaces/siri/`), all generated from the single committed `surfaces/openapi.json`. Each is a client of the daemon's OpenAPI surface — no business logic. See `surfaces/README.md`.
- **`public/`** — the thin-client PWA: vanilla ES modules that call the daemon's REST API, with offline read snapshots, an offline move queue, and cycle-count mode. The daemon serves it as static files.
- **`vision/`** — the tiered photo identification/grading pipeline (`numislens_vision`, own venv). A pure REST client of the daemon + LAN GPU endpoints (OCR + VLM) behind a deterministic agreement gate that never writes a guessed value; disagreements escalate for human/assistant adjudication. See the Vision section below.

### Core CLI quickstart

The `core/` package installs a `numislens` console script (`pip install -e core`). The database resolves from `--db`, then `$NUMISLENS_DB`, then `~/.local/share/numislens/numislens.db`.

```bash
numislens init                                          # create/migrate the database
numislens add --series "Peace Dollar" --year 1921 \
  --mint P --composition 4 --value-basis melt           # returns an accession, e.g. NL-000001
numislens melt update                                   # fetch dual-source spot, recompute melt values
numislens melt status                                   # latest spots + portfolio melt + daily change
```

Melt fetching is keyless and fail-loud: it never fabricates a price and exits non-zero on source disagreement (>2%), staleness (>48h), or network errors. Read commands (`show`, `find`, `set gaps`, `set status`, `melt status`) accept `--json`.

## Features

- **Collection ledger**: every coin is an accession (`NL-000001…`) in one SQLite database — the source of truth for all surfaces.
- **Inventory browser**: search and filter coins by series, year, mintmark, and location; drill into any coin's detail.
- **Add with photos**: create a coin and capture obverse / reverse / edge / slab images from the device camera.
- **Locations**: nest cabinets → boxes → trays → slots (and albums → pages → pockets); every coin lives in exactly one, and moves are recorded as events.
- **Set-completion boards**: visual album grids per set with filled/gap slot chips, key-date markers, and an assign-coin picker.
-   **Melt dashboard**: deterministic, keyless precious-metal melt values with a dual-source spot cross-check — never fabricated, fail-loud on source disagreement or staleness.
-   **Reference values & appraisal worklist**: curated, source-cited value datasets (wheat-cent keys, the Washington quarter keys melt can't price, Jefferson nickel surprises) apply read-time via exact-match lookups — no interpolation, never written onto coins. The report's worklist answers the inheritor's real question: *which of these 400 coins deserve eyes first?*
- **Value-watch**: token-efficient, three tiers cheapest-first — daily melt (automatic), a weekly market digest that fans one search out to staleness flags (`/watch/digest`), and a monthly top-value watchlist sweep. Staleness is metadata (it never changes a stored value); a ≥10% spot move auto-flags hybrid/numismatic coins, and an appraisal clears the flag. Optional keyless ntfy push on big moves.
- **Offline-first**: cached read snapshots (always shown with an OFFLINE banner) and a queue for offline coin moves that replays in order when connectivity returns.
- **Cycle-count mode**: warehouse-style reconciliation of a location's expected contents against what is physically present, with a copyable report.
- **QR labels**: printable accession labels (PDF) whose QR codes deep-link into the app.
- **Installable PWA**: works offline, installs on mobile and desktop.

## Technology Stack

- **Frontend**: Vanilla JavaScript ES modules, HTML5, CSS3 — no framework, no build step
- **Architecture**: Progressive Web App (thin client over the daemon's OpenAPI surface)
- **Backend**: FastAPI daemon (`daemon/`) over the `numislens_core` SQLite ledger
- **Offline support**: Service Worker asset cache + IndexedDB read snapshots and write queue

## Running the PWA

The PWA is static and is served by the daemon — there is no separate build step or Node dependency.

```bash
python3 -m venv .venv && . .venv/bin/activate     # most distros require a venv (PEP 668)
pip install -e core -e daemon
export NUMISLENS_TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
echo "token: $NUMISLENS_TOKEN"                     # you'll paste this into the app
numislens-daemon --db ~/.local/share/numislens/numislens.db
```

Then open **http://127.0.0.1:8471** in a modern browser (or the machine's LAN/Tailscale address from your phone), go to **Settings**, and paste the bearer token to connect — every view is gated until a token is saved. The app is intended to be reached over LAN/Tailscale only; never expose the daemon to the open internet.

## PWA views and modules

- `public/index.html` — app shell
- `public/js/app.js` — shell, navigation (with a responsive "More" overflow menu), routing, the offline status bar, and move-queue replay
- `public/js/api.js` — bearer-authenticated client for the daemon REST API
- `public/js/router.js` — hash router
- `public/js/store.js`, `public/js/offline.js` — IndexedDB snapshot cache and offline move queue
- `public/js/views/` — `inventory`, `coin`, `add`, `locations`, `sets`, `rolls`, `albums`, `melt`, `report`, `cyclecount`, `settings`
- `public/js/photo.js`, `public/js/money.js`, `public/js/tree.js` — camera capture, dollar-input parsing, location-tree helpers
- `public/sw.js` — service worker (its precache list is versioned per release)

## Vision — photo identification (Phase 4)

`vision/` runs a tiered photo pipeline over a coin's stored obverse/reverse images and **never writes a guessed value** — the direct descendant of the fabrication bug this project exists to avoid.

- **Tiers.** T1 OCR (PaddleOCR-VL) reads the stamped text; T2 VLM (Qwen) does four separate micro-calls (series/denomination/country, date read **digit-by-digit**, mintmark, condition bucket); an optional T3 (Gemma) is a config-driven third voter. Every model output is canonicalized deterministically at the boundary (enum paraphrases, JSON key-renaming, MS-numerics → condition bucket).
- **Agreement gate.** Year and mintmark are accepted only when the tiers agree (OCR+VLM unanimity, or 2-of-3 with Gemma); any year that hits a **key-date** slot demands unanimity across all available tiers. Series and grade come from the VLM alone (grade is a photo-grade condition bucket `AG…UNC`, never MS-numeric). Disagreements **escalate** — shown with every tier's reading for a human/assistant (Tier 3) to adjudicate; nothing is guessed.
- **Writeback (fail-safe).** Accepted fields fill the coin only where NULL (never overwrite user data); grade is written with `grade_source` plus an append-only photo-grade appraisal; escalations write no identification and instead mark the coin **stale** (via the digest endpoint) so it surfaces in `watch/status`.

Setup and run (own venv; a pure REST client — do not install `core` here):

```bash
python3 -m venv vision/.venv && . vision/.venv/bin/activate && pip install -e vision
export NUMISLENS_URL=http://127.0.0.1:8471 NUMISLENS_TOKEN=...   # the daemon
# endpoints (defaults shown): comma-separated OCR boxes w/ failover, one VLM,
# optional Gemma (unset = skipped, its absence is reported in results)
export VISION_OCR_URLS=http://ocr-host-a:8080,http://ocr-host-b:8080
export VISION_VLM_URL=http://vlm-host:8088
# export VISION_GEMMA_URL=http://gemma-host:8090   # optional third voter

numislens-vision identify NL-000123     # read-only: print the gated result
numislens-vision process  NL-000123     # + fail-safe writeback for one coin
numislens-vision process  --pending     # every unidentified coin with images
numislens-vision status                 # collection-wide vision counts
```

Claude reaches the same pipeline through the MCP `identify_coin` tool (read-only; install `vision` into the MCP venv). ChatGPT/Gemini surfaces cannot run it (it is a local worker, not a cloud endpoint) — they upload photos and the worker identifies later.

**Benchmark.** `vision/bench/` scores the pipeline against your own staged coins (date and mintmark scored separately and strictly; per-tier and post-gate accuracy; escalation rate). Copy `bench/ground_truth.example.json` to `bench/ground_truth.json`, photograph ~20 known coins, and run `python bench/runner.py bench/ground_truth.json`. See `vision/bench/README.md` for the protocol; the one synthetic entry only proves the harness runs and is excluded from accuracy.

## Testing

- Core: `cd core && python3 -m pytest`
- Daemon: `cd daemon && python3 -m pytest`
- Vision: `cd vision && python3 -m pytest` (own venv; mocked HTTP, no live GPUs)
- MCP: `cd surfaces/mcp && python3 -m pytest` (own venv; requires `pip install -e vision`)
- PWA smoke: `python3 scripts/e2e_smoke.py` (scratch daemon + temp DB) and `python3 scripts/check_sw_files.py` (service-worker precache list vs. files on disk)
- OpenAPI artifact: `python3 scripts/export_openapi.py` regenerates `surfaces/openapi.json` and asserts every `/api/v1` path is present and bearer-secured

## Deployment

See `ops/README.md` for deployment: user-level systemd units for the daemon and the daily melt update, Litestream/dump backups (`ops/BACKUP.md`), and the LAN/Tailscale exposure guidance.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details.

## Acknowledgments

- Local vision models: PaddleOCR-VL (OCR tier) and Qwen VL–family models (cross-vote tier) behind the agreement gate — any OpenAI-compatible endpoints work
- Spot prices from keyless public sources (gold-api.com primary, Yahoo Finance cross-check)
- Numismatic grading buckets follow common industry practice; nothing here replaces a professional appraisal

## Support

For support, please open an issue in the GitHub repository.