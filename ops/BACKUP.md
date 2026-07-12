# NumisLens backup & restore

## Continuous replication (primary): Litestream

Litestream streams the SQLite WAL to S3 or Backblaze B2 offsite. Replication is continuous; there is no API in the read path for normal app use.

1. Copy `ops/litestream.yml` and replace all `REPLACE_*` placeholders.
2. Export credentials (never commit these):

   ```bash
   export LITESTREAM_ACCESS_KEY_ID=your-key-id
   export LITESTREAM_SECRET_ACCESS_KEY=your-secret-key
   ```

3. Run replication:

   ```bash
   litestream replicate -config ops/litestream.yml
   ```

## Nightly dump (alternative): sqlite3 .dump

A plain cron or systemd-timer alternative without Litestream:

```bash
sqlite3 ~/.local/share/numislens/numislens.db .dump | gzip > numislens-$(date +%F).sql.gz
```

You can push dumps into a private Gitea repo for versioned offsite history if desired.

## Restore drill

**Litestream restore** (in-place or to a scratch path):

```bash
litestream restore -config ops/litestream.yml ~/.local/share/numislens/numislens.db
# or: litestream restore -config ops/litestream.yml -o /tmp/restored.db
```

**Dump restore:**

```bash
gunzip -c numislens-YYYY-MM-DD.sql.gz | sqlite3 restored.db
```

**Verify after restore:** open the restored DB and confirm integrity, e.g. `numislens --db restored.db melt status` or `sqlite3 restored.db 'SELECT COUNT(*) FROM coins;'`.

Practice the restore before you need it.
