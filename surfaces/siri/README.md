# Apple Shortcuts — NumisLens

These Shortcuts call the NumisLens daemon REST API directly from your iPhone — no App
Store app, no OpenAPI import, no business logic on the phone. Every request is a plain
HTTPS call with a bearer token; the daemon on your home machine (or VPS) is the sole
source of truth.

**Reachability:** your phone must reach the daemon over your tailnet (Tailscale) or
via Tailscale Funnel. Replace the placeholder host below with your real base URL.

**Security:** store the bearer token inside each Shortcut (a **Text** action) and treat
it as a secret. Anyone with your phone and the Shortcut can call your ledger. Use a
**dedicated, revocable** daemon token (`NUMISLENS_TOKEN`) rather than sharing your
primary credential. The daemon binds to localhost / Tailscale only — never port-forward
it raw to the public internet without TLS and auth.

## Operating rules (echo)

Match the discipline in `surfaces/chatgpt/instructions.md`:

- **Fail loud, never fabricate.** On errors, show the response body — do not pretend
  success.
- **Quick-add** (`POST /api/v1/coins/quick`) parses text **deterministically** on the
  daemon (no LLM). Always read and speak the **`unresolved`** array. Unknown locations
  are listed there and **not** auto-created.
- **Grade is never inferred.** Quick-add never sets `grade_bucket`.
- **Money:** integer cents in JSON; speak the daemon's **`*_display`** strings (e.g.
  `"$5.00"`) — never recompute dollars from cents in the Shortcut.
- **Melt routine:** use **`GET /api/v1/melt/status`** (stored spots, no live fetch).
  Do **not** wire **`POST /api/v1/melt/update`** into a Siri routine (live external
  fetch; at most once daily elsewhere).

---

## Shared setup

Use this in **every** recipe below.

| Item | Value |
|------|--------|
| **Base URL** | `https://numislens.YOUR-TAILNET-NAME.ts.net` — replace `YOUR-TAILNET-NAME` with your Tailscale machine name (same placeholder as `surfaces/openapi.json` `servers[0].url`). |
| **Bearer token** | Add a **Text** action near the top of each Shortcut containing your daemon token (no `Bearer` prefix in the Text — only the raw token string). |
| **Authorization header** | In **Get Contents of URL → Headers**, add: **Key** `Authorization`, **Value** `Bearer` + space + the **Text** magic variable from the token action. Shortcuts: insert **Text** token variable after typing `Bearer ` in the header value field. |

All `/api/v1/*` paths require this header. Omitting it returns **401**.

**Error-handling pattern (all recipes):** Shortcuts **Get Contents of URL** does not
expose HTTP status codes directly. Branch on the **shape** of the JSON body instead of
status:

1. After **Get Contents of URL**, add **If** → condition **Dictionary** → **Has Any Value** (or **Has Key** for the success marker each recipe defines).
2. **Otherwise** → **Show Alert** with title `NumisLens error` and message = the raw
   **Contents of URL** (or **Get Dictionary Value** `detail` when the body is a JSON
   object with a `detail` key). **Stop** the shortcut in the alert branch so failures
   are never spoken as success.

---

## RECIPE 1 — Add Coin

**Purpose:** dictate free text → `POST /api/v1/coins/quick` → speak accession and
`unresolved` items.

**Success response shape** (HTTP 200):

```json
{
  "parsed": { "...": "fields written to the ledger" },
  "unresolved": ["box 9", "composition", "unrecognized: \"shiny\""],
  "created": "NL-000042",
  "coin": { "accession_no": "NL-000042", "value_est_display": null, ... }
}
```

`unresolved` carries two kinds of entries: things the parser recognized but could
not map (an unknown location, an uncertain composition, a malformed amount) **and**
`unrecognized: "..."` entries echoing any leftover dictated text the parser could
not consume (an unknown word, a second year, a floating mint letter). Speaking the
whole list — as step 10 below does — tells you exactly which words of your
dictation were ignored.

**Failure** (HTTP 422 when neither series nor year parsed): body includes `detail` with
`message`, `parsed`, and `unresolved` — **no coin is created**.

### Steps

1. **Dictate Text** — prompt: `Coin to add`  
   *(Or **Ask for Input** → Input Type **Text**, prompt `Coin to add`.)*  
   Example utterance: `1943 steel cent, box 3 slot 12, paid $4`.

2. **Text** — paste your bearer token (raw token only). Name this mentally “Token”.

3. **Dictionary** — add one item: **Key** `text`, **Value** = magic variable from step 1
   (Dictated Text).

4. **Get Contents of URL**
   - **URL:** `https://numislens.YOUR-TAILNET-NAME.ts.net/api/v1/coins/quick`
   - **Method:** `POST`
   - **Headers:**
     - `Authorization` → `Bearer ` + Token (Text variable from step 2)
     - `Content-Type` → `application/json`
   - **Request Body:** `JSON` → dictionary from step 3

5. **If** → **Contents of URL** (from step 4) → **Dictionary** → **Has Key** → `created`
   - **Then** (success branch):
     6. **Get Dictionary Value** — Dictionary: Contents of URL; Key: `created` → this is
        the accession string (e.g. `NL-000042`).
     7. **Get Dictionary Value** — Dictionary: Contents of URL; Key: `unresolved`.
     8. **If** → **unresolved** (step 7) → **Count** → **is** `0`
        - **Then:** set variable **Unresolved speech** to the Text `nothing unresolved`.
        - **Otherwise:** **Repeat with Each** over **unresolved** → **Text** each item,
          **Combine Text** with separator `, ` → **Unresolved speech**.
     9. **Text** — template: `Added coin ` + **created** (step 6) + `. Unresolved: ` +
        **Unresolved speech** (step 8).
     10. **Speak Text** — speak the Text from step 9 (user hears the accession, every
         unresolved phrase, and every `unrecognized: "..."` leftover-text entry — so
         nothing you dictated is silently ignored).
   - **Otherwise** (error branch):
     11. **If** → Contents of URL → **Dictionary** → **Has Key** → `detail`
         - **Then:** **Get Dictionary Value** Key `detail` → **Show Alert** (title
           `Quick-add failed`, message = detail).
         - **Otherwise:** **Show Alert** (title `Quick-add failed`, message = raw
           **Contents of URL**).
     12. **Stop This Shortcut**.

### Hey Siri

> “Hey Siri, Add Coin” — then dictate e.g. `1885 Morgan dollar CC, paid $120`.

---

## RECIPE 2 — Find Coin

**Purpose:** filter coins by **exact** series name via `GET /api/v1/coins?series=…`.

**Important — no free-text search:** the daemon has **no** fuzzy or full-text search
endpoint. This recipe uses the **`series` query parameter** on `GET /api/v1/coins`
only. The value must match the **canonical series string** stored in the ledger (exact
match), e.g. `Morgan Dollar`, `Peace Dollar`, `Washington Quarter`, `Lincoln Wheat
Cent`. Saying “morgan” or “1921 silver dollar” will **not** search — only an exact
`series=` filter returns rows. For year, mintmark, or other filters, the API also
accepts `year`, `mintmark`, `denomination`, `grade_bucket`, `composition_id`, and
`location_id` query params, but this Shortcut uses **`series` only**.

**Success response:** JSON **array** of coin objects. Each coin includes (among DB
fields) at least: `accession_no`, `year`, `mintmark`, `denomination`, `series`,
`location_id`, `value_est_cents`, `value_est_display`, `cost_basis_cents`,
`cost_basis_display`. Empty array `[]` means no coins match.

### Steps

1. **Dictate Text** — prompt: `Series to find`  
   *(Or **Ask for Input** → Text, prompt `Series to find`.)*  
   Say the canonical name, e.g. `Morgan Dollar`.

2. **Text** — bearer token (shared setup).

3. **Get Contents of URL**
   - **URL:** `https://numislens.YOUR-TAILNET-NAME.ts.net/api/v1/coins`
   - **Method:** `GET`
   - **Headers:** `Authorization` → `Bearer ` + Token
   - **URL Query Parameters:** add parameter **Name** `series`, **Value** = dictated
     text from step 1

4. **If** → **Contents of URL** → **List** → **Has Any Value**
   - **Then:**
     5. **Set variable** `Results` → empty Text.
     6. **Repeat with Each** → **Item** = Contents of URL (the coin array):
        - **Get Dictionary Value** from **Repeat Item** → Key `accession_no`.
        - **Get Dictionary Value** → Key `year` (may be empty).
        - **Get Dictionary Value** → Key `mintmark` (may be empty).
        - **Text** — `accession_no`, space, `year`, space, `mintmark` (omit blank
          parts if you prefer).
        - **Combine Text** — append each line to `Results` with newline separator.
     7. **Speak Text** — `Results`.
   - **Otherwise** (empty list **or** non-list error body):
     8. **If** → Contents of URL → **Dictionary** → **Has Key** → `detail`
        - **Then:** **Show Alert** — message = **Get Dictionary Value** `detail`.
        - **Otherwise (empty list):** **Speak Text** — `no coins found for ` + dictated
          series from step 1.
     9. **Stop This Shortcut** on alert path only.

### Hey Siri

> “Hey Siri, Find Coin” — then say `Morgan Dollar` (exact series name).

---

## RECIPE 3 — Melt Today

**Purpose:** read **stored** melt portfolio and day-over-day spot change via
`GET /api/v1/melt/status` — **no** live spot fetch.

**Success response shape** (HTTP 200):

```json
{
  "spots": {
    "XAG": {
      "price_usd_cents": 3125,
      "price_display": "$31.25",
      "source": "gold-api",
      "fetched_at": "2026-07-12T14:00:00+00:00"
    },
    "XAU": { "...": "..." },
    "XPT": null
  },
  "portfolio": {
    "total_cents": 123456,
    "total_display": "$1,234.56",
    "by_metal": {
      "XAG": { "cents": 50000, "display": "$500.00" },
      "XAU": { "cents": 73456, "display": "$734.56" }
    }
  },
  "delta": {
    "XAG": { "latest_cents": 3125, "prior_cents": 3100, "pct": 0.8064516129032258 },
    "XAU": { "latest_cents": 265000, "prior_cents": 264000, "pct": 0.3787878787878788 }
  }
}
```

- **`spots`:** keys are metals `XAU`, `XAG`, `XPT` (each object or `null` if no stored
  spot).
- **`portfolio`:** speak **`total_display`** — never divide `total_cents` by 100 in the
  Shortcut.
- **`delta`:** per-metal spot change vs prior day; **`pct`** is percent change (float).
  Empty `{}` when there is no prior day to compare.

### Steps

1. **Text** — bearer token (shared setup).

2. **Get Contents of URL**
   - **URL:** `https://numislens.YOUR-TAILNET-NAME.ts.net/api/v1/melt/status`
   - **Method:** `GET`
   - **Headers:** `Authorization` → `Bearer ` + Token

3. **If** → **Contents of URL** → **Dictionary** → **Has Key** → `portfolio`
   - **Then:**
     4. **Get Dictionary Value** — Dictionary: Contents of URL; Key: `portfolio`.
     5. **Get Dictionary Value** — Dictionary: portfolio (step 4); Key: `total_display`
        → variable **Melt total** (e.g. `$1,234.56`).
     6. **Get Dictionary Value** — Dictionary: Contents of URL; Key: `delta` →
        variable **Delta**.
     7. **If** → **Delta** → **Dictionary** → **Has Any Value**
        - **Then** (compare the three metals — only `XAU`, `XAG`, `XPT` exist):
          8. For each metal in `XAU`, `XAG`, `XPT` where **Delta** has that key:
             - **Get Dictionary Value** from **Delta** → Key `XAU` (repeat for `XAG`,
               `XPT`; skip keys that do not exist).
             - **Get Dictionary Value** from that metal dict → Key `pct`.
             - **Calculate** — **Absolute Number** of `pct` → variable e.g.
               `abs_pct_XAU`.
          9. **If** `abs_pct_XAU` ≥ `abs_pct_XAG` and `abs_pct_XAU` ≥ `abs_pct_XPT`
             (and XAU exists) → **Winner metal** `XAU`, **Winner pct** = raw `pct` from
             delta `XAU`.
          10. Else **If** `abs_pct_XAG` ≥ `abs_pct_XPT` (and XAG exists) → **Winner
              metal** `XAG`, **Winner pct** = raw `pct` from delta `XAG`.
          11. Else → **Winner metal** `XPT`, **Winner pct** = raw `pct` from delta
              `XPT`.
          12. **Speak Text** — `Portfolio melt is ` + **Melt total** + `. Biggest daily
              spot move: ` + **Winner metal** + ` ` + **Winner pct** + ` percent.`
              *(Shortcuts may format the float; that is fine.)*
        - **Otherwise** (empty delta):
          13. **Speak Text** — `Portfolio melt is ` + **Melt total** + `. No prior day
              to compare.`
   - **Otherwise** (error branch):
     14. **If** → Contents of URL → **Has Key** → `detail` → **Show Alert** with
         `detail`; else **Show Alert** with raw Contents of URL.
     15. **Stop This Shortcut**.

Use **`total_display`** and metal **`display`** fields from the API only — **never**
recompute dollar amounts from `*_cents` in the Shortcut.

### Hey Siri

> “Hey Siri, Melt Today” — speaks stored portfolio melt and the largest daily spot
> percent change.

**Reminder:** this recipe uses **stored** spots (`GET /api/v1/melt/status`). Do **not**
add `POST /api/v1/melt/update` to a Siri Shortcut or daily automation; live spot fetch
belongs in a deliberate, infrequent job (at most once per day), not a voice routine.
