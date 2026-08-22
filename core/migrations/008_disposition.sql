-- Coin disposition lifecycle (sell-prep). Additive only.
--
-- A coin moves owned -> for_sale -> sold (or discarded), tracked on the coin
-- row like rolls.status. Realized sale facts are recorded at the moment of the
-- transition; the append-only events table carries every state change as a
-- 'disposition' event, so history stays reconstructable even after a
-- correction moves a coin back to owned. Rows are NEVER deleted (a discarded
-- coin keeps its identity and audit trail).
-- No BEGIN/COMMIT: the migration runner wraps this file in a single atomic
-- transaction (see db.py).
ALTER TABLE coins ADD COLUMN disposition TEXT NOT NULL DEFAULT 'owned'
  CHECK (disposition IN ('owned', 'for_sale', 'sold', 'discarded'));
ALTER TABLE coins ADD COLUMN sold_date TEXT;
ALTER TABLE coins ADD COLUMN sold_price_cents INTEGER;
ALTER TABLE coins ADD COLUMN sold_venue TEXT;
