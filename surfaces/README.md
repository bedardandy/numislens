# NumisLens assistant surfaces

The daemon OpenAPI spec at `/api/v1/openapi.json` is the single integration artifact. Every assistant surface is a thin skin over the same REST API and bearer token. No surface embeds business logic.

## What exists (Phase 2b)

- **mcp/** — a FastMCP stdio server (package `numislens-mcp`, module `numislens_mcp`) exposing 15 tools over the REST API. See `mcp/mcp-config.example.json` to wire it into Claude Code (`.mcp.json`) or Claude Desktop. It is a REST client only (no DB access).
- **claude/SKILL.md** — a Claude Code skill teaching the operating rules (melt/valuation via tools not arithmetic; confirm year+mintmark before adding; integer-cents money; no fabricated grades or values; vision ID is a later phase).

## What's coming (Phase 5)

- ChatGPT Custom GPT Action (consumes the OpenAPI directly)
- Gemini Gem (same OpenAPI)
- Siri/Apple Shortcuts hitting REST
- `AGENTS.md` for other coding agents

All are additional skins over the identical OpenAPI surface.

## The single integration artifact

The daemon serves its OpenAPI JSON at `GET /api/v1/openapi.json` (interactive docs at `/api/v1/docs`). New surfaces should be generated from that spec rather than hand-maintaining a parallel client. Authenticate with a bearer token in the `Authorization` header. The daemon binds localhost / Tailscale only and must never be port-forwarded raw.
