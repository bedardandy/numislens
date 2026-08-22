# AGENTS.md — NumisLens

Directive for coding agents (Codex, Claude, Cursor, etc.) working in this repo.
Read this first, then `surfaces/claude/SKILL.md` for the assistant operating
rules. If a change would violate an invariant below,
stop and reconsider — these are load-bearing.

## What this is

A coin collection is a **ledger, not an app.** One canonical SQLite database
(`core/`) and one small FastAPI daemon (`daemon/`) are the source of truth;
every other surface (PWA, Claude MCP/skill, ChatGPT Action, Gemini Gem, Siri
Shortcuts) is a **thin skin over the same OpenAPI**. The single integration
artifact is the daemon's OpenAPI JSON at `GET /api/v1/openapi.json` (exported to
`surfaces/openapi.json`). Do not add a parallel client or duplicate business
logic in a surface.

## Full tree

```
numislens/
├── AGENTS.md                      # this file
├── README.md                      # product + PWA overview
├── LICENSE (GPL-3.0)                # deployment/ops docs live in ops/README.md
├── core/                          # the ledger — dependency-free, source of truth
│   ├── numislens_core/
│   │   ├── db.py                  # migration runner + connection helpers
│   │   ├── ledger.py              # Ledger: coins, locations, sets, appraisals, events, images
│   │   ├── manifests.py           # set-manifest load/validate
│   │   ├── melt.py                # keyless dual-source spot fetch + melt recompute
│   │   └── cli.py                 # `numislens` console script
│   ├── migrations/                # 001_initial … 006_albums (rolls, album imports)
│   ├── sets/                      # set manifests (JSON) + manifest.schema.json
│   └── tests/                     # pytest: cli, ledger, manifests, melt, migrations_smoke
├── daemon/                        # FastAPI REST + OpenAPI + bearer auth
│   ├── numislens_daemon/
│   │   ├── app.py                 # create_app(); mounts routers + static PWA
│   │   ├── auth.py                # constant-time bearer check
│   │   ├── config.py              # token + settings resolution
│   │   ├── deps.py                # per-request Ledger dependency
│   │   ├── errors.py              # core exceptions -> HTTP status handlers
│   │   ├── quickadd.py            # DETERMINISTIC free-text parser (no LLM)
│   │   ├── schemas.py             # Pydantic request bodies (extra="forbid")
│   │   ├── serializers.py         # pure response shaping (adds *_display)
│   │   ├── labels.py              # QR label-sheet PDF rendering
│   │   └── routers/               # coins, locations, sets, melt, labels, watch
│   └── tests/                     # pytest: auth, coins, images, labels, locations, melt, quickadd, sets, validation
├── surfaces/                      # thin assistant skins over the REST API
│   ├── openapi.json               # generated spec (regen: scripts/export_openapi.py)
│   ├── README.md
│   ├── claude/SKILL.md            # Claude Code skill — the operating rules
│   ├── mcp/                       # FastMCP stdio server (REST client only) + tests
│   ├── chatgpt/                   # Custom GPT Action: README + instructions.md
│   ├── gemini/                    # Gemini Gem: README + instructions.md
│   └── siri/                      # Apple Shortcuts recipes: README.md
├── vision/                        # Phase-4 tiered photo ID/grade pipeline
│   ├── numislens_vision/          # own package + venv; pure REST client
│   │   ├── config, endpoints, canon, tiers, gate, pipeline
│   │   ├── writeback.py           # fail-safe fill-null writeback + escalation stale
│   │   ├── worker.py, __main__.py # `numislens-vision` identify/process/status
│   │   └── ...                    # NO core import, NO direct DB
│   ├── bench/                     # ground-truth benchmark harness + protocol
│   └── tests/                     # pytest: canon, gate, endpoints, pipeline, writeback, worker
├── public/                        # the PWA — vanilla ES modules, no build step
│   ├── index.html, manifest.json, sw.js
│   └── js/ (api, app, router, store, offline, photo, money, tree, views/*)
├── ops/                           # systemd units, Litestream, backup docs (never auto-enabled)
├── scripts/                       # export_openapi.py, e2e_smoke.py, check_sw_files.py, gen_icons.py
└── tests/js/                      # Node test(s) for PWA helpers
```

## Invariants (do not break)

1. **Fail loud, never fabricate.** This tool's entire reason to exist is honest
   inventory/appraisal. Never invent an identity, grade, value, composition, or
   default for a fact you were not given. On missing data, surface it (an
   `unresolved` list, a 422, an OFFLINE banner) — do not guess. The deleted
   `generateFallbackResponse` (random coin on API failure) is the anti-pattern.
   **One deliberate exception:** the optional ntfy push (`NUMISLENS_NTFY_URL`,
   `melt.push_notification`) logs-not-raises on failure — a dead notifier must
   never block the melt update or the ledger. It is the only non-fatal outbound
   error path, and the only outbound call besides the two spot sources.
2. **Grade is never inferred.** `grade_bucket` is set only from a photo pipeline
   or a human/TPG appraisal, never parsed from text or guessed.
3. **Composition only when numismatically certain.** See `quickadd.py`
   `_certain_composition`: steel cent (metal named in the word), or Morgan/Peace
   dollars *within their .900-silver date range*. Otherwise leave it null and
   list it unresolved. Certain rules live as documented data, not prose.
4. **Integer cents everywhere.** All money is integer cents in the DB and API
   (`*_cents` fields; `500` = $5.00). Responses add companion `*_display`
   strings ("$5.00") via `serializers.py`. Never store or compute money as a
   float.
5. **Append-only history.** `events` and `appraisals` are append-only ledgers —
   the audit trail *is* the provenance. Add rows; never overwrite or delete them.
   Moves, adds, and appraisals all write an `events` row. Value-watch staleness
   (`coins.stale_since`/`stale_reason`) is transient METADATA, not history: it
   never changes `value_est_cents`, and `record_appraisal` clears it atomically
   with the appraisal insert.
6. **Zero-dependency core.** `numislens_core` imports only the Python stdlib
   (sqlite3, urllib, etc.). Do not add third-party runtime deps to `core/`. The
   quick-add parser is stdlib regex only.
7. **Thin daemon, thin surfaces.** Router handlers marshal to/from the `Ledger`
   and serializers; business logic lives in `core/`. Surfaces (MCP, GPT, Gemini,
   Siri, PWA) are REST clients with NO business logic — the PWA must not embed
   valuation/melt math.
8. **Unknown fields 422.** Request schemas use `extra="forbid"`; unknown keys
   return HTTP 422, never a silent drop (assistant callers guess field names —
   e.g. `mint` for `mintmark` — and silent drops lose data).
9. **Locations are never auto-created.** Quick-add resolves a mentioned location
   against existing labels; an unknown location is returned unresolved. Create
   locations explicitly.
10. **Security posture.** Bearer token + bind to localhost/Tailscale only; never
    port-forward the daemon raw. The DB never lives on someone else's cloud.
    Every `/api/v1/*` path requires the bearer token.
11. **No vision/LLM code in core/ or daemon/.** The tiered ID/grade pipeline
    lives ONLY in `vision/` — a separate package/venv that is a pure REST client
    of the daemon + LAN GPU endpoints (no `numislens_core` import, no direct DB).
    `core/` and `daemon/` stay LLM-free: the daemon's `PATCH
    /api/v1/coins/{accession}` writeback is deterministic (fill-NULL only, never
    overwrites), and grade set there is legitimate per invariant 2 (a photo
    pipeline is an allowed grade source, tagged via `grade_source`). The gate in
    `vision/gate.py` NEVER emits a guessed value — disagreements escalate.

## Test suites (keep green)

Run all three before committing anything that touches their area:

```bash
cd core            && python3 -m pytest -q
cd daemon          && python3 -m pytest -q     # use the daemon venv's python
cd surfaces/mcp    && python3 -m pytest -q     # needs its own venv + `pip install -e vision`
cd vision          && python3 -m pytest -q     # own venv; no live network
node --test tests/js/*.test.js                  # glob form (the bare-dir form breaks on Node 22)
node --test tests/js/money.test.mjs
python3 scripts/e2e_smoke.py                    # scratch daemon + temp DB, boots nothing external
python3 scripts/check_sw_files.py               # sw.js precache list vs files on disk
node --check public/js/<file>.js                # syntax-check any edited PWA module
```

Install for local dev: `pip install -e core -e daemon`; the MCP server has its
own package/venv (`pip install -e surfaces/mcp`). A bearer token must be set
(`NUMISLENS_TOKEN=...`) or `create_app` refuses to start.

## Commit conventions

- Conventional commits scoped by component: `feat(daemon): …`, `feat(core): …`,
  `feat(surfaces): …`, `fix(pwa): …`, `test(core): …`, `docs: …`.
- One coherent change per commit; keep suites green at each commit.
- End commit messages with the required trailer:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Local commits only unless a human explicitly asks to push. The canonical
  development remote is private; the public GitHub repo is a reviewed snapshot —
  **nothing reaches it without a PII/hygiene gate and human sign-off.**

## Pointers

- Operating rules for assistants: `surfaces/claude/SKILL.md` (the ChatGPT/Gemini
  instruction files teach the same substance in adapted wording).
- Regenerate the OpenAPI artifact after any route/schema change:
  `python3 scripts/export_openapi.py` (asserts the expected `/api/v1` path
  count, all secured — keep its constant in step with route changes).
