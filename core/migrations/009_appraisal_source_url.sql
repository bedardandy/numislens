-- Appraisal provenance: an optional citation URL on appraisal records.
--
-- When an appraisal is backed by an observable source (an auction result, a
-- dealer listing, a price-guide page), the link belongs IN the record — the
-- audit trail IS the provenance (AGENTS.md invariant 5). Nullable, additive
-- only; append-only triggers are untouched.
-- No BEGIN/COMMIT: the migration runner wraps this file in a single atomic
-- transaction (see db.py).
ALTER TABLE appraisals ADD COLUMN source_url TEXT;
