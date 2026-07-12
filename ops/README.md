# NumisLens ops

User-level systemd units for scheduling daily `numislens melt update` runs. These are **user** services (not system units) and are installed **without sudo**.

## Install

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/numislens-melt.service ops/systemd/numislens-melt.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now numislens-melt.timer
systemctl --user list-timers numislens-melt.timer
journalctl --user -u numislens-melt.service -n 50
```

The timer fires daily around 13:00 with up to 30 minutes of jitter. If the machine was off at the scheduled time, `Persistent=true` runs a catch-up on next boot.

For the timer to run when you are not logged in, enable lingering:

```bash
loginctl enable-linger $USER
```

## Fail-loud behavior

The melt service exits non-zero on source disagreement (>2%), staleness (>48h), or network errors. Check `journalctl --user -u numislens-melt.service` for details.

## Value-watch (Phase 6)

Value-watch keeps appraisals cheap: melt is repriced automatically every day
(the timer above), a **weekly digest** fans one web search out to staleness
flags, and a **monthly watchlist sweep** re-appraises only the top-value coins.
The daemon/core stay LLM-free — the assistant does the search + distillation
*outside* and feeds structured findings into the deterministic
`POST /api/v1/watch/digest` endpoint.

### Optional keyless push (ntfy)

Set `NUMISLENS_NTFY_URL` to a full ntfy.sh topic URL and `numislens melt update`
(and `POST /api/v1/melt/update`) will POST a plain-text alert when any metal
moves more than 3% day-over-day, or when a ≥10% spot move newly flags coins
stale. Off when unset; a failed push is logged, never fatal.

```bash
# pick a private topic name; then subscribe on your phone via the ntfy app
echo 'NUMISLENS_NTFY_URL=https://ntfy.sh/numislens-<your-random-suffix>' >> ~/.config/numislens/daemon.env
# for the melt timer, add the same line to the melt service Environment= or its env file
```

### Weekly digest as a Claude scheduled task

Create a weekly scheduled task with this prompt verbatim (it searches, distills,
and calls the deterministic sink — one call, no per-coin searches):

```
Run the NumisLens weekly market digest.

1. Do ONE web search for notable US coin market movers, recent auction records,
   and coin-series news from the past week.
2. Distill what you find into a list of items, each affecting coins I actually
   hold. Each item is exactly one target plus a reason and a source:
     - {"series": "<a series I own>", "reason": "<why it moved>", "source_note": "<citation>"}
     - {"set_id": "<set key or id>", "reason": "...", "source_note": "..."}
     - {"accessions": ["NL-000123"], "reason": "...", "source_note": "..."}
   Only use a series name that appears in my collection; never guess.
3. Call submit_digest(items) ONCE with that list. If it returns a 422 for an
   unknown series, drop that item (use the known-series list it returns) and
   resubmit. Do NOT run per-coin web searches.
4. Report how many coins were marked stale per item.

Do not re-appraise anything and do not recompute melt — this run only flags
coins for later lazy re-appraisal.
```

### Monthly watchlist sweep reminder

Once a month, sweep only the top-value coins (never the long tail):

```
Call get_watchlist(25). For EACH of those coins only, do a quick market check
with the cheapest model tier and record the result with record_appraisal
(include a rationale and source). Recording an appraisal clears that coin's
stale flag. Do not touch any coin outside the watchlist.
```

## Backups

See [ops/BACKUP.md](BACKUP.md) for Litestream replication and dump-based backup/restore.

## NumisLens daemon (Phase 2a)

Install the daemon package (console script `numislens-daemon`):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e core -e daemon
# or: pipx install -e core -e daemon
```

Generate a bearer token and store it in `NUMISLENS_TOKEN` or in `~/.config/numislens/token` (chmod 600):

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(32))"
```

For the systemd unit below, put the token in `~/.config/numislens/daemon.env` as `NUMISLENS_TOKEN=...` (chmod 600 that file).

Run manually (binds localhost only):

```bash
numislens-daemon --db PATH --host 127.0.0.1 --port 8471
```

The daemon listens on `127.0.0.1` and must **never** be port-forwarded raw to the internet.

Expose over Tailscale (TLS on your tailnet; cloud assistants use the bearer token):

```bash
tailscale serve --bg 8471
```

Install the user unit (not enabled by this repo):

```bash
cp ops/systemd/numislens-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now numislens-daemon
```

## Assistant surfaces

The `surfaces/` directory holds thin assistant skins over the daemon's REST API
(see `surfaces/README.md`). The generated `surfaces/openapi.json` is the single
integration artifact.

- **Claude** — MCP server (`surfaces/mcp/`, installed separately, see below) +
  `surfaces/claude/SKILL.md`.
- **ChatGPT** — Custom GPT Action (`surfaces/chatgpt/`) importing `openapi.json`.
- **Gemini** — Gem (`surfaces/gemini/`) importing `openapi.json` (curl fallback).
- **Siri** — Apple Shortcuts recipes (`surfaces/siri/`) hitting REST directly.

**Funnel guidance:** the local PWA, Claude MCP, and Siri (on your tailnet) reach
the daemon over LAN/Tailscale. Cloud assistants (ChatGPT, Gemini) call from the
vendor's servers, so they need the daemon reachable publicly — expose it with a
Tailscale Funnel (`tailscale funnel 8471`) or a Cloudflare tunnel, never a raw
port-forward, and mint a **dedicated bearer token** per cloud surface so it can
be revoked independently. The SQLite ledger never leaves your machine.

The Claude MCP server is installed separately from the daemon; it is a pure REST
client and talks to the daemon over HTTP with the same bearer token.

### Install the MCP server

```bash
python3 -m venv surfaces/mcp/.venv && . surfaces/mcp/.venv/bin/activate
pip install -e surfaces/mcp          # console script: numislens-mcp
```

The MCP server reads two environment variables:

- `NUMISLENS_URL` — daemon base URL (default `http://127.0.0.1:8471`; set it to
  wherever the daemon actually listens, e.g. your
  `tailscale serve` URL).
- `NUMISLENS_TOKEN` — the same bearer token the daemon uses (required; the
  server exits with a clear message if it is unset).

### Wire it into Claude Code (`.mcp.json`)

Add a `numislens` entry to the project's `.mcp.json` (or run it via
`claude mcp add`). Template stanza in `surfaces/mcp/mcp-config.example.json`:

```json
{
  "mcpServers": {
    "numislens": {
      "command": "numislens-mcp",
      "args": [],
      "env": {
        "NUMISLENS_URL": "http://127.0.0.1:8471",
        "NUMISLENS_TOKEN": "REPLACE_WITH_DAEMON_TOKEN"
      }
    }
  }
}
```

### Wire it into Claude Desktop

Add the same `mcpServers.numislens` stanza to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`) and
restart Claude Desktop. Use the absolute path to the `numislens-mcp` console
script (inside `surfaces/mcp/.venv/bin/`) if it is not on Claude Desktop's PATH.

### Claude skill

`surfaces/claude/SKILL.md` is a Claude Code skill teaching the operating rules
(melt via tools not arithmetic, integer-cents money, confirm year+mintmark,
no fabricated grades/values). Install it under your Claude skills directory.
