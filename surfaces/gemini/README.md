# Google Gemini Gem — NumisLens

A thin skin over the NumisLens daemon REST API. The single integration artifact is
`surfaces/openapi.json` (also served live at `GET /api/v1/openapi.json`). This Gem
has no business logic of its own — every read and write goes through the daemon with
your bearer token.

## Setup

### Primary path: Gem with OpenAPI tools

When your Gemini account/tier supports Actions or OpenAPI tool import:

1. In Gemini: **Gems → New Gem** (or edit an existing Gem).
2. **Import the OpenAPI schema** — upload or paste `surfaces/openapi.json` from this
   repo.

   **Before importing**, edit `servers[0].url` — replace the placeholder host:

   ```json
   "url": "https://numislens.YOUR-TAILNET-NAME.ts.net"
   ```

   with your real reachable daemon base URL (see
   [Reachability and security](#reachability-and-security) below).

   The spec defines 22 secured `/api/v1/*` paths (health, coins, locations, sets, melt,
   labels).

3. **Authentication** — configure a **Bearer** authorization header with your
   NumisLens daemon token (`NUMISLENS_TOKEN`). The daemon expects
   `Authorization: Bearer <token>` on every `/api/v1/*` request.

4. **Instructions** — copy the full contents of `instructions.md` in this directory
   into the Gem's instructions field. That file teaches the same operating rules as
   `surfaces/claude/SKILL.md` and `surfaces/chatgpt/instructions.md` — adapted for
   Gemini over the REST API.

5. **Test** — ask the Gem something simple that hits the API, e.g. “What is my melt
   status?” or “List my coin sets.” If tool calls fail, check reachability and the
   bearer token first.

### Fallback path: explicit REST calls (no OpenAPI import)

Some Gemini tiers do not yet support OpenAPI/Action import. In that case, instruct the
Gem to drive the daemon with explicit HTTP requests. Responses are JSON with integer
`*_cents` fields plus companion `*_display` strings (e.g. `"$5.00"`).

Examples the user can adapt (replace `HOST` and `<token>`):

```bash
# Stored melt status (no live spot fetch)
curl -sS -H 'Authorization: Bearer <token>' \
  'https://HOST/api/v1/melt/status'

# Quick-add from free text (deterministic parser on the daemon)
curl -sS -X POST -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"text":"1943 steel cent, box 3 slot 12, paid $4"}' \
  'https://HOST/api/v1/coins/quick'
```

Paste `instructions.md` into the Gem instructions so the model follows the same
operating rules (integer cents, `unresolved` relay, no invented grades, etc.) even
when it constructs requests manually.

Do **not** use Google Apps Script for this surface — the Gem should call the NumisLens
daemon directly.

## Reachability and security

**Gemini tool calls reach your endpoint from Google's servers**, not from your browser.
The daemon must therefore be reachable from the public internet for tools to work.

Recommended approaches:

- **Tailscale Funnel** — expose the daemon HTTPS endpoint on your tailnet hostname
  (the placeholder in `openapi.json` is shaped for this).
- **Cloudflare Tunnel** (or similar) — terminate TLS and forward to the local daemon.

**Do not** raw port-forward the daemon to the open internet. NumisLens security
posture is bearer token plus bind-to-localhost/Tailscale only; the SQLite ledger
never lives on someone else's cloud.

**Tradeoff:** exposing the API for Gemini means Google's infrastructure can reach
your daemon when the Gem invokes a tool. Mitigate with:

1. A **dedicated bearer token** minted only for this Gemini surface — revoke it
   independently without affecting your PWA, MCP, ChatGPT, or other clients.
2. Funnel/tunnel access controls where your provider allows them.
3. Treat the token like a password; rotate if leaked.

For day-to-day use on your own machine or tailnet without public exposure, use the
PWA or Claude MCP surface instead — they talk to the daemon locally.

## What this surface does not do

- Photo identification and automated grading are **not built yet** (a later phase).
  The Gem must not present guessed IDs or grades from images as fact.
- No parallel business logic — melt math, quick-add parsing, and ledger rules live
  in `core/` and `daemon/` only.

## Related files

- `instructions.md` — Gem system prompt (paste into Instructions)
- `../openapi.json` — OpenAPI schema (edit `servers[0].url`, then import)
- `../chatgpt/instructions.md` — same operating substance for ChatGPT Actions
- `../claude/SKILL.md` — same operating substance for Claude Code / MCP
