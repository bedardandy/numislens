---
name: numislens
description: >
  Manage a physical coin collection through the NumisLens MCP tools. Use when the user asks about their coin collection, inventory, melt or portfolio value, where a coin is stored, set completion gaps, or adding or appraising coins — e.g. "my coin collection", "melt value", "coin inventory", "where is my <coin>", "set gaps", "silver melt", "add a coin", "portfolio value".
---

# NumisLens

You have NumisLens MCP tools: `find_coins`, `get_coin`, `add_coin`, `quick_add`, `move_coin`, `locate_coin`, `list_locations`, `add_location`, `list_sets`, `set_gaps`, `set_status`, `portfolio_value`, `melt_status`, `melt_update`, `record_appraisal`, `get_label_pdf`, `watch_status`, `list_stale`, `get_watchlist`, `submit_digest`. Follow these rules.

## Money and melt questions

- Answer melt and valuation questions with `melt_status` and `portfolio_value`. NEVER compute melt or portfolio figures by arithmetic when a tool provides them.
- All money is integer cents in the API (500 = $5.00). Every money field has a companion `*_display` string ("$5.00") — quote the display string to the user.
- NEVER quote a dollar value for a coin unless it came from a tool response or an explicit appraisal record. If neither exists, say the value is not yet established.
- `melt_status` reads STORED spot prices (no network) — use it for routine questions. `melt_update` hits LIVE external spot sources and rewrites every coin melt; run it AT MOST once daily, and prefer `melt_status`.

## Adding coins

- Always confirm the year and mintmark with the user BEFORE writing a coin — key dates are ~100x sensitive (a 1914 Lincoln cent vs a 1914-D is a completely different value). Do not assume.
- Money fields are integer cents (`cost_basis_cents`, `value_est_cents`). Convert dollars the user says into integer cents before calling `add_coin`.
- The API rejects unknown fields with HTTP 422 — use the exact field names from the `add_coin` tool (e.g. `mintmark`, not `mint`).
- NEVER invent a grade. Leave `grade_bucket` null unless it came from a photo or an appraisal. Do not fabricate defaults for facts you were not given.

## Quick-add (free text)

- `quick_add` takes one phrase (e.g. "1943 steel cent, box 3 slot 12, paid $4") and parses it DETERMINISTICALLY on the daemon — no LLM, no guessing. Prefer it for fast dictated capture; use `add_coin` when you already have structured fields.
- ALWAYS read the response `unresolved` array and tell the user what it lists. A location named in the text that does not already exist is returned unresolved and is NOT auto-created — create it with `add_location`, then `move_coin` (or re-run). An uncertain composition or malformed amount also lands there.
- If neither a series nor a year parsed, `quick_add` returns a 422 with what it did and didn't understand and creates nothing — relay that; do not retry with invented fields.
- It never sets a grade and only sets a composition when numismatically certain (e.g. "steel cent", or a Morgan/Peace dollar within its silver date range). Still confirm year and mintmark with the user for key-date sensitivity.

## Identifying coins from photos

- The vision identification/grading pipeline is NOT built yet (it is a later phase). Do NOT guess a coin identity, grade, or valuation from a photo and present it as fact.
- When the user shows or describes a coin to identify: capture what is actually known (record the coin with only the confirmed fields), note that photos were provided, and tell the user that automated identification/grading is not available yet.

## Value-watch etiquette (token efficiency) — operating procedure

The collection is watched with three mechanisms, cheapest first. **Never
re-appraise the whole collection.** Follow this cadence:

1. **Melt is automatic (daily, 0 tokens).** The daemon reprices every melt-basis
   coin from spot on a cron. NEVER recompute melt yourself and NEVER re-appraise
   a melt-basis coin (junk silver, bullion) — its value simply *is* melt. For
   melt questions call `melt_status` (stored, no network); run `melt_update` at
   most once daily.

2. **Weekly digest (one sweep, one call).** Do ONE web-search sweep — "US coin
   market movers, auction records, series news" — distill the results into
   structured items, and submit them in a SINGLE `submit_digest(items)` call.
   Never run per-coin searches for this. Each item names EXACTLY ONE target
   (`series`, `set_id`, or `accessions`) plus a `reason`, and should cite a
   `source_note` — do NOT mark stale on a hunch. `series` is a case-insensitive
   exact match against series you actually hold; an unknown series returns 422
   listing what DOES exist and marks nothing (relay it, don't retry a guess).
   `submit_digest` only flags coins stale; it changes no values.

3. **Monthly watchlist sweep (top-N only).** Call `get_watchlist(25)` and do an
   individual market check for ONLY those top-value coins, using the cheapest
   model tier. Record each result with `record_appraisal` (rationale + source);
   recording an appraisal CLEARS that coin's staleness. Never sweep the long
   tail unprompted.

4. **Stale coins re-appraise lazily.** A coin flagged stale (see `list_stale` /
   `watch_status`) is a re-appraisal TODO, not a changed value — its stored
   value is unchanged until you record an appraisal. Re-appraise a stale coin
   when it is next viewed or when the user asks, not eagerly.

5. **Never appraise the long tail unprompted.** Low-value coins are re-appraised
   on demand only. Spot moves and the digest do the watching for free.

Spot silver moving ±10% automatically marks all hybrid/numismatic coins of that
metal stale (their premiums track spot) — you do not need to trigger that.

## Recording appraisals

- `record_appraisal` writes an APPEND-ONLY record (history is never overwritten). `value_cents` and `token_cost` are integer cents.
- Before you ASSERT a significant or changed value for a coin, back it with an appraisal record (or a tool-sourced melt/portfolio figure). No unbacked value claims.

## Physical workflow

- Every coin has exactly ONE location. After any physical move, call `move_coin` immediately so the ledger matches reality.
- Use `locate_coin` to answer "where is my <coin>?" (returns a path like Cabinet A > Box B2 > Tray 3 > Slot 14).
- Use `list_locations` to see the storage hierarchy and `add_location` to create new tiers.
- Printed labels: `get_label_pdf` writes a QR label-sheet PDF to a local path (by location or by accession list).

## Sets

- `list_sets` shows completion counts; `set_gaps` lists the missing date/mint slots; `set_status` gives a filled/total summary. Use these for "what am I missing?" questions.
