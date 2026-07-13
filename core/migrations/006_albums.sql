-- Album / coin-folder photo import (Phase: album import). Additive only.
--
-- A user photographs the pages of a coin folder/album (Whitman/Dansco style).
-- Each import gathers page photos; each analyzed page yields slot readings
-- (year + mint parsed from the printed label, plus a filled/empty/uncertain
-- judgement). Review happens against these rows; commit turns the import into a
-- real set + coin rows. NOTHING here stores a value; the platform's
-- NO-FABRICATION rule lives in how fill_state is judged (uncertain is a
-- first-class state and commit refuses to guess it filled).
--
-- No BEGIN/COMMIT: the migration runner (db.py) wraps this file plus its
-- bookkeeping row in a single atomic transaction.

CREATE TABLE album_imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'analyzed', 'committed', 'discarded')),
  set_id INTEGER REFERENCES sets(id),
  created_at TEXT NOT NULL
);

CREATE TABLE album_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_id INTEGER NOT NULL REFERENCES album_imports(id),
  seq INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  page_title TEXT,
  page_type TEXT CHECK (page_type IN ('page', 'not_a_page') OR page_type IS NULL),
  analyzed_at TEXT,
  UNIQUE (import_id, content_hash)
);

CREATE TABLE album_page_slots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES album_pages(id),
  slot_index INTEGER NOT NULL,
  label_text TEXT NOT NULL DEFAULT '',
  year INTEGER,
  mint TEXT,
  note TEXT NOT NULL DEFAULT '',
  fill_state TEXT NOT NULL
    CHECK (fill_state IN ('filled', 'empty', 'uncertain')),
  confidence REAL,
  source TEXT NOT NULL CHECK (source IN ('vision', 'human')),
  UNIQUE (page_id, slot_index)
);

CREATE INDEX idx_album_pages_import ON album_pages(import_id);
CREATE INDEX idx_album_page_slots_page ON album_page_slots(page_id);
