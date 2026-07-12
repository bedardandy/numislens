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
