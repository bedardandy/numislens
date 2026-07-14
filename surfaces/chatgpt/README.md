# ChatGPT Custom GPT — NumisLens Action

A thin skin over the NumisLens daemon REST API. The single integration artifact is
`surfaces/openapi.json` (also served live at `GET /api/v1/openapi.json`). This GPT
has no business logic of its own — every read and write goes through the daemon with
your bearer token.

## Setup

### 1. Create the GPT

In ChatGPT: **Explore GPTs → Create**. Open **Configure → Actions**.

### 2. Import the OpenAPI schema

Paste or upload `surfaces/openapi.json` from this repo.

**Before importing**, edit `servers[0].url` — replace the placeholder host:

```json
"url": "https://numislens.YOUR-TAILNET-NAME.ts.net"
```

with your real reachable daemon base URL (see [Reachability and security](#reachability-and-security) below).

The spec defines 39 secured `/api/v1/*` paths (health, coins, locations, sets, rolls, albums, melt, labels, report, watch).

### 3. Authentication

In the Actions auth settings:

- **Authentication type:** API Key
- **Auth Type:** Bearer
- **API Key:** paste your NumisLens daemon bearer token (`NUMISLENS_TOKEN`)

The daemon expects `Authorization: Bearer <token>` on every `/api/v1/*` request.

### 4. Instructions

Copy the full contents of `instructions.md` in this directory into the GPT's
**Instructions** box. That file teaches the same operating rules as
`surfaces/claude/SKILL.md` — adapted for ChatGPT Actions over the REST API.

### 5. Test

After saving, ask the GPT something simple that hits the API, e.g. “What is my melt
status?” or “List my coin sets.” If Actions fail, check reachability and the bearer
token first.

## Reachability and security

**ChatGPT Actions call your endpoint from OpenAI's servers**, not from your browser.
The daemon must therefore be reachable from the public internet for Actions to work.

Recommended approaches:

- **Tailscale Funnel** — expose the daemon HTTPS endpoint on your tailnet hostname
  (the placeholder in `openapi.json` is shaped for this).
- **Cloudflare Tunnel** (or similar) — terminate TLS and forward to the local daemon.

**Do not** raw port-forward the daemon to the open internet. NumisLens security
posture is bearer token plus bind-to-localhost/Tailscale only; the SQLite ledger
never lives on someone else's cloud.

**Tradeoff:** exposing the API for ChatGPT means OpenAI's infrastructure can reach
your daemon when the GPT invokes an Action. Mitigate with:

1. A **dedicated bearer token** minted only for this ChatGPT surface — revoke it
   independently without affecting your PWA, MCP, or other clients.
2. Funnel/tunnel access controls where your provider allows them.
3. Treat the token like a password; rotate if leaked.

For day-to-day use on your own machine or tailnet without public exposure, use the
PWA or Claude MCP surface instead — they talk to the daemon locally.

## What this surface does not do

- Photo identification and automated grading run in the LOCAL vision pipeline
  (`vision/`, via `numislens-vision` or the Claude MCP tools), not on this cloud
  surface.
  The GPT must not present guessed IDs or grades from images as fact.
- No parallel business logic — melt math, quick-add parsing, and ledger rules live
  in `core/` and `daemon/` only.

## Related files

- `instructions.md` — GPT system prompt (paste into Instructions)
- `../openapi.json` — Action schema (edit `servers[0].url`, then import)
- `../claude/SKILL.md` — same operating substance for Claude Code / MCP
