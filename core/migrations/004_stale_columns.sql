-- Value-watch staleness metadata (Phase 6). Additive only: two nullable
-- columns on coins. Staleness is METADATA, never a value: marking a coin stale
-- never changes value_est_cents. A coin is "stale" when a market signal (a
-- weekly digest hit or a >=10% spot move) suggests its numismatic/premium value
-- may have drifted and warrants a lazy re-appraisal. record_appraisal clears it.
-- Append-only tables (events, appraisals) are untouched.
ALTER TABLE coins ADD COLUMN stale_since TEXT;
ALTER TABLE coins ADD COLUMN stale_reason TEXT;
