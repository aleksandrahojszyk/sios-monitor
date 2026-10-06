# SIOS monitor — handoff for a new Cursor chat

Workspace: `/Users/aleksandrahojszyk/Projects/sios-monitor`  
Owner: Aleksandra (Designer; prefer working in code). Commit/push only when asked.

**Read next:** `docs/SIOS_RESEARCH.md` (verified public-search behaviour, 2026-10-06), `docs/COLLECTOR_NOTES.md` (robots.txt / pacing), `README.md` (how to run).

Do **not** re-investigate SIOS or rebuild the collector unless live behaviour contradicts the research doc or a test fails.

---

## Product goal and intended use

Build a monitoring application for **public SIOS environmental information cards** in Poland (https://system.sios.pl/search/common), focused first on European beaver (`bóbr` / *Castor fiber*) and other protected-species cases.

Intended pipeline (later phases): find cards → store metadata → classify → help prepare **information-access requests** when the underlying file is not public.

**Current phase only:** collect and normalize **public** card metadata. Explicitly out of scope until asked: frontend, dashboard, login, AI classification, case management, request-letter generation, Postgres/Supabase, e-delivery, Playwright, non-public documents.

---

## What we learned about public SIOS search

Verified, not guessed (`docs/SIOS_RESEARCH.md`):

- Results are **server-rendered HTML** from `GET /search/common`. Not Fetch/XHR/REST/GraphQL for the result list.
- Nationwide search: `iid=0` or omit `iid`. Positive `iid` scopes one **institution** (gmina/starostwo/etc.), not a voivodeship.
- Empty nationwide search reported **354 954** cards (SIOS licensees, not every Polish office).
- Unique identifier: numeric ID in `/documents/details/id/{id}`. Card number `2047/2026` is **not** unique nationally (two different IDs shared it).
- No CSRF on the public form. `PHPSESSID` is set but **not required**. No CAPTCHA on this path.
- Location dropdowns use extra HTML AJAX (`/ajax/districts/...`, `/ajax/communities/...`); the collector does not need them for nationwide keyword search.
- `/documents/advancedsearch` **302**s to `/index/charakt` without login — do not use it.
- Keyword engine is **not** stemming/synonyms. Independent queries, then **union by `sios_id`**:

  | Query | Hits (2026-10-06) |
  |---|---:|
  | `bóbr` / `bobr` | 3115 (same first page) |
  | `bobry` | 414 |
  | `Castor fiber` | 749 |
  | `bóbr europejski` | 104 (AND of tokens) |
  | `zwierząt chronionych` | 21 |

- `robots.txt`: `User-Agent: *` / `Disallow: /`. Legal/org approval required before large or scheduled crawls. No evasion.

---

## Architecture and tech stack

Python package `sios-monitor` (`pyproject.toml`): **Python 3.7+**, `httpx>=0.24,<0.25`, BeautifulSoup4, PyYAML, pytest. Local machine has **Python 3.7.1**; SQLite here is too old for `ON CONFLICT` upsert, so storage uses INSERT vs UPDATE.

Flow:

1. `SiosClient.search` → HTML  
2. `parse_search_page` → unique `SearchHit`s  
3. pagination stop (`pagination_decision`)  
4. `SiosClient.fetch_card` → HTML fragment  
5. `parse_detail_page` → `CardRecord`  
6. `Storage.upsert_card` + `keyword_matches`

Pacing: sleep so requests are ~**1.5s** apart (`config/collector.yaml`). Retry 408/425/429/5xx and network errors with exponential backoff. User-Agent is set. `--delay` and `--no-raw` override config.

CLI: `python -m src.sios.collector --keyword "bóbr"` | `--all-keywords` | `--card-id 449913`  
Optional: `--max-pages`, `--delay`, `--log-level`, `--config`, `--keywords-file`.

---

## Implemented so far

Working collector (do not rewrite): nationwide GET search, defensive pagination, detail fetch, raw HTML snapshots, SQLite incremental upsert, JSON logs on stderr, YAML keywords, fixture tests.

**Live pilot (do not expand without instruction):**  
`python -m src.sios.collector --keyword "bóbr" --max-pages 2`  
→ 2 pages, **60 unique cards**, 60 new, 0 errors, SIOS reported total **3115**, stop reason `max_pages`. Raw files may exist locally under `data/` (gitignored).

Not implemented: downloading `/documents/download/id/{fileId}` during collection (URLs only), geo-filtered search, sort via `/search/extend`, UI.

---

## Important files

| Path | Role |
|---|---|
| `docs/SIOS_RESEARCH.md` | Source of truth for SIOS HTTP/HTML behaviour |
| `docs/COLLECTOR_NOTES.md` | robots.txt, pacing, RODO on clerk names |
| `docs/HANDOFF.md` | This file |
| `README.md` | Setup and CLI |
| `config/collector.yaml` | base_url, UA, delay 1.5s, timeout 30, retries 4, `results_per_page: 30`, `iid: 0`, `max_pages: 1000`, paths |
| `config/keywords.yaml` | Editable query groups: species / protected_species / interventions |
| `src/sios/client.py` | httpx GET, pacing, retries |
| `src/sios/search_parser.py` | Result table → `SearchHit` |
| `src/sios/detail_parser.py` | `table.table1` labels → `CardRecord` + `raw_fields` |
| `src/sios/models.py` | Dataclasses; `pagination_decision` |
| `src/sios/storage.py` | SQLite schema and upsert |
| `src/sios/collector.py` | Orchestration + argparse `main` |
| `src/sios/config.py` | Load YAML; `PROJECT_ROOT` = repo root |
| `src/sios/logging_utils.py` | JSON log formatter (`extra={"sios": {...}}`) |
| `tests/` | Fixture HTML + unit tests (no live SIOS) |
| `data/raw/search/`, `data/raw/details/` | Optional snapshots (`search_bobr_page_1.html`, `{id}.html`) |
| `data/normalized/sios.sqlite` | Local DB |

`.gitignore` excludes `.venv`, pytest cache, `data/raw/**/*.html`, `*.sqlite`. Keep `.gitkeep` dirs.

---

## Scraping / parsing logic and assumptions

**Search** (`parse_search_page`): find `<table>` whose first `<th>` contains `Nr karty`; skip header rows; require ≥5 `<td>`; take `a[href*=documents/details/id/N]` (prefer class fancybox). Dedup IDs **within** the page (each card appears ~3 times). Columns: (0) number, (1) type + “Tematy:”, (2) name then snippet, (3) `YYYY-MM-DD` and/or case mark, (4) `woj / powiat / gmina` (empty segments → `None`). Total count: regex `Liczba wyświetlanych pozycji: N`.

**Details** (`parse_detail_page`): two-cell rows in `table.table1` → `raw_fields[label] = text`. Empty string → `None` for normalized fields. Dates mapped: wpływ→`received_at`, wydania→`issued_at`, zatwierdzenia→`approved_at`, zamieszczenia→`published_at`, wprowadzenia→`entered_at`. Location from Województwo/Powiat/Gmina. Related cards from “Numery kart innych dokumentów w sprawie”. Attachments from `documents/download/id/{fileId}`. Single-cell colspan rows with “Brak załączników” or a download link → `raw_fields["Wersja elektroniczna"]`.

**Fill-in:** if a detail field is missing, collector copies from the search hit. Search extras stored under `raw_fields["_search"]`.

**Assumptions:** nationwide keyword search is enough for beaver monitoring; default `id_doctype=0` and `id_doctopic=0` (all types/topics); HTML structure stays as documented; we collect **cards**, not administrative cases.

---

## Search parameters and pagination

Client always sends: `keywords`, `iid` (config, default 0), `id_doctype=0`, `id_doctopic=0`, `page`, `results` (default **30**), `submitSearch=Szukaj`.

Documented UI page sizes: 10, 20, 30, 50, 100. Research saw 200/500 work; **do not default to those** (may be unsupported later).

Pagination: 1-based `page`. Last overflow page **repeats** the previous ID set (page 105 == 104 for `bóbr`). `pagination_decision` stops on:

1. `empty_page`  
2. `repeated_page` (ID set == previous page)  
3. `no_new_ids`  
4. `max_pages` (CLI or config 1000)  
5. `http_error`

Never stop only because HTML is non-empty.

---

## Data model (collected fields)

**SQLite `cards`** PK `sios_id`: `card_number`, `year`, `document_name`, `document_type`, `case_reference`, `authority` (Nazwa organu), `location`, `dates_json`, `source_url`, `first_seen_at`, `last_seen_at`, `raw_fields_json`.

**`keyword_matches`:** `(sios_id, keyword)` unique.

**`collection_runs`:** per-keyword run stats (`pages_processed`, `cards_found`, `new_cards`, `status`, `error`).

Normalized dates keys: `received_at`, `issued_at`, `approved_at`, `published_at`, `entered_at`. Literal page text (e.g. `nie dotyczy`) is kept; empty → `null`.

`raw_fields` also holds all Polish labels (temat, zakres przedmiotowy, wytworzył, siedziba, telefon, e-mail, zniszczeniu, ostateczny, uwagi, informacja może być udostępniona, podstawa prawna, zakres, clerk name, …) plus `_attachments`, `_related_cards`, `_search`.

Dedup **only** on `sios_id`. Re-run: update last_seen + fields, preserve first_seen, `INSERT OR IGNORE` new keywords. Do not delete cards missing from a later query.

---

## Tests and verification

`pytest` — **15 passed** last run. Fixtures in `tests/fixtures/`. Coverage:

- ID extraction; same card number ≠ same card; empty search; within-page href dupes  
- Detail parse of 449913-like HTML; missing optionals → null; attachment `file_id`  
- Pagination repeat / empty / no_new_ids  
- SQLite update-in-place; multiple keywords  
- FakeClient collector: repeat last page does not loop; `--max-pages 1`; second run 0 new cards  

Live: 60-card `bóbr` sample, HTTP 200 throughout, ~1.5s spacing. All 60 had number/year/name/type/case/authority/voivodeship; 2 missing powiat, 6 missing gmina; 32 related-card links; 3 attachment links.

---

## Limitations and open questions

- Approval not obtained for full 3115-hit crawl or `--all-keywords`.  
- Rate limits still **unverified**.  
- Whether `id_doctopic` bit flags can be OR-ed: untested.  
- Completeness of SIOS vs all Polish beaver cases: unknown.  
- `CardRecord.search_metadata` exists on the dataclass but is unused; extras go in `raw_fields["_search"]`.  
- Pilot SQLite/HTML were saved **before** the colspan “Wersja elektroniczna” parser tweak; next live fetch will pick that up.  
- Clerk names in `raw_fields` = personal data (RODO).

---

## Git

- Remote: `https://github.com/aleksandrahojszyk/sios-monitor.git`  
- Branch: `cursor/sios-public-metadata-collector` tracking `origin/cursor/sios-public-metadata-collector`  
- Commits: `3a82bc1` collector; `baeae2e` short handoff; this file expands the handoff for a new coding agent  
- Remote tracks this branch; do not assume `main` has the same history  

---

## Do not revisit

- Playwright for public GET search/details  
- Card number / title / case mark as primary key  
- Treating one `iid` as national  
- Default `results` of 200/500  
- Empty-page-only pagination stop  
- Frontend, AI, Postgres, request letters  
- `/documents/advancedsearch`  
- Auth/CAPTCHA/IP-rotation bypass  
- Full nationwide crawl without an explicit go-ahead  

---

## Exact next steps (recommended order)

1. If this file changed: commit/push only if the user asks.  
2. Get organisational/legal OK before any crawl beyond small `--max-pages` pilots (`COLLECTOR_NOTES.md`).  
3. After OK: run remaining `config/keywords.yaml` queries with a **page cap**, same 1.5s delay, union by `sios_id`; log overlap vs `bóbr`.  
4. Optional analysis on SQLite (counts, missing geo, `Informacja może być udostępniona`, attachment flags) — still no UI.  
5. Optional later: download **only** already-linked `/documents/download/id/{fileId}` with the same client pacing.  
6. New phase (not now): case-level grouping, classification, access-request drafts.

Start work in this repo on the existing branch. Extend `src/sios/*` and tests; do not scaffold a second collector.
