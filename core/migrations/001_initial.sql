CREATE TABLE compositions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  metal TEXT CHECK (metal IN ('XAG','XAU','XPT') OR metal IS NULL),
  fineness REAL,
  precious_weight_ozt REAL,
  nominal_weight_g REAL,
  notes TEXT
);
CREATE TABLE locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id INTEGER REFERENCES locations(id),
  kind TEXT NOT NULL,
  label TEXT NOT NULL
);
CREATE TABLE coins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  accession_no TEXT UNIQUE NOT NULL,
  series TEXT,
  year INTEGER,
  mintmark TEXT,
  denomination TEXT,
  country TEXT DEFAULT 'US',
  composition_id INTEGER REFERENCES compositions(id),
  weight_g REAL,
  diameter_mm REAL,
  grade_bucket TEXT CHECK (grade_bucket IN ('AG','G','VG','F','VF','XF','AU','UNC','PROOF') OR grade_bucket IS NULL),
  grade_source TEXT CHECK (grade_source IN ('local-vlm','cross-vote','cloud','human','tpg') OR grade_source IS NULL),
  tpg_cert TEXT,
  cost_basis_cents INTEGER,
  acquired_date TEXT,
  acquired_source TEXT,
  value_est_cents INTEGER,
  value_basis TEXT CHECK (value_basis IN ('melt','numismatic','hybrid') OR value_basis IS NULL),
  last_appraised TEXT,
  appraisal_confidence REAL,
  location_id INTEGER REFERENCES locations(id),
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  set_key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  series TEXT,
  composition_ref TEXT
);
CREATE TABLE set_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  set_id INTEGER NOT NULL REFERENCES sets(id),
  year INTEGER NOT NULL,
  mint TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  key_date INTEGER NOT NULL DEFAULT 0,
  coin_id INTEGER REFERENCES coins(id),
  UNIQUE (set_id, year, mint, note)
);
CREATE TABLE spot_prices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metal TEXT NOT NULL CHECK (metal IN ('XAU','XAG','XPT')),
  price_usd_cents INTEGER NOT NULL,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  UNIQUE (metal, fetched_at, source)
);
CREATE TABLE appraisals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coin_id INTEGER NOT NULL REFERENCES coins(id),
  appraised_by TEXT NOT NULL,
  appraised_at TEXT NOT NULL,
  grade_bucket TEXT,
  value_cents INTEGER,
  value_basis TEXT,
  rationale TEXT,
  token_cost INTEGER,
  confidence REAL
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coin_id INTEGER REFERENCES coins(id),
  event_type TEXT NOT NULL,
  at TEXT NOT NULL,
  detail TEXT
);
CREATE TABLE coin_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coin_id INTEGER NOT NULL REFERENCES coins(id),
  kind TEXT CHECK (kind IN ('obverse','reverse','edge','slab')),
  content_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TRIGGER appraisals_no_update BEFORE UPDATE ON appraisals BEGIN SELECT RAISE(ABORT,'appraisals are append-only'); END;
CREATE TRIGGER appraisals_no_delete BEFORE DELETE ON appraisals BEGIN SELECT RAISE(ABORT,'appraisals are append-only'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
