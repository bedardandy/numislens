# NumisLens assistant surfaces

The daemon OpenAPI spec at `/api/v1/openapi.json` is the single integration artifact. Every assistant surface is a thin skin over the same REST API and bearer token. No surface embeds business logic.

## What exists

- **openapi.json** — the committed, generated OpenAPI spec (39 secured `/api/v1` paths). Regenerate it after any route/schema change (see below); ChatGPT and Gemini import it directly.
- **mcp/** — a FastMCP stdio server (package `numislens-mcp`, module `numislens_mcp`) exposing 30 tools over the REST API (including `quick_add`, coin rolls, and album photo imports). See `mcp/mcp-config.example.json` to wire it into Claude Code (`.mcp.json`) or Claude Desktop. It is a REST client only (no DB access).
- **claude/SKILL.md** — a Claude Code skill teaching the operating rules (melt/valuation via tools not arithmetic; confirm year+mintmark before adding; integer-cents money; no fabricated grades or values; quick-add unresolved contract; vision ID is a later phase).
- **chatgpt/** — Custom GPT with Actions: `README.md` (setup) + `instructions.md` (system prompt mirroring SKILL.md).
- **gemini/** — Gemini Gem: `README.md` (OpenAPI import where supported, curl fallback) + `instructions.md` (same substance).
- **siri/** — `README.md` with three field-by-field Apple Shortcuts recipes (Add Coin, Find Coin, Melt Today) hitting REST directly.

The Claude, ChatGPT, and Gemini instruction files teach the SAME operating substance in adapted wording; keep them in sync when the rules change.

## The single integration artifact

The daemon serves its OpenAPI JSON at `GET /api/v1/openapi.json` (interactive docs at `/api/v1/docs`). New surfaces are generated from that spec rather than hand-maintaining a parallel client. Authenticate with a bearer token in the `Authorization` header. The daemon binds localhost / Tailscale only and must never be port-forwarded raw; cloud assistants (ChatGPT, Gemini) reach it through a Tailscale Funnel (or Cloudflare tunnel) with a dedicated, independently-revocable token.

### Regenerate `openapi.json`

```bash
python3 scripts/export_openapi.py      # imports create_app(), dumps surfaces/openapi.json
```

The script generates the spec in-process (no server boot), injects the `bearerAuth` scheme and a `servers[0].url` tailnet placeholder (edit it to your host before importing), and asserts every `/api/v1` path is present and secured. Run it whenever routes or schemas change and commit the result.
