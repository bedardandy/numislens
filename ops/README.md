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
