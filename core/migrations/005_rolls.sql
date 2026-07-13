-- Coin rolls (bulk holdings). A roll is an unsearched/partially-searched stack
-- of same-denomination coins tracked as a single unit until pulled apart into
-- individual coins. Additive only: a new table plus its append-only guard is
-- unnecessary here because rolls are mutable (count decrements as coins are
-- pulled); the audit trail lives in the append-only events table (coin_id NULL,
-- event_type like 'roll:created' / 'roll:pulled'). No BEGIN/COMMIT: the
-- migration runner wraps this file in a single atomic transaction (see db.py).
CREATE TABLE rolls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  roll_no TEXT UNIQUE NOT NULL,
  denomination TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'US',
  count INTEGER NOT NULL CHECK (count >= 0),
  series TEXT,
  year INTEGER,
  composition_id INTEGER REFERENCES compositions(id),
  variant TEXT,
  status TEXT NOT NULL DEFAULT 'unopened' CHECK (status IN ('unopened','searching','searched','exhausted')),
  cost_basis_cents INTEGER,
  acquired_date TEXT,
  acquired_source TEXT,
  location_id INTEGER REFERENCES locations(id),
  notes TEXT,
  created_at TEXT NOT NULL
);
