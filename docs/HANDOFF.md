# SIOS monitor — Cursor chat handoff

Read this first, then `docs/SIOS_RESEARCH.md` and `docs/COLLECTOR_NOTES.md`. Do not re-investigate SIOS architecture unless implementation contradicts the research doc.

## Project goal

Monitor **publicly available** Polish SIOS environmental information cards (source: https://system.sios.pl/search/common), starting with European beaver and other protected-species cases. Long-term: collect metadata, classify, later help prepare information-access requests.

**This phase is only public metadata collection.** Not in scope yet: frontend, dashboard, auth, AI classification, case management, document-request generation, database UI, e-delivery, browser automation, non-public files.

## Current architecture

Public SIOS search is **server-rendered HTML GET**, not JSON/REST/GraphQL.

- Search: `GET https://system.sios.pl/search/common?keywords=…&iid=0&page=N&results=30`
- Card: `GET https://system.sios.pl/documents/details/id/{numericId}`
- Nationwide scope: `iid=0` (or omit `iid`). Positive `iid` is one institution, not a voivodeship.
- Unique key: **numeric SIOS ID**. Card numbers like `2047/2026` are **not** globally unique.
- Session cookie is issued but not required. No CSRF on public search. No CAPTCHA observed.
- Overflow pages **repeat the last page** instead of returning empty.

Collector: Python CLI (`httpx` + BeautifulSoup + SQLite). Conservative delay (default **1.5s**). Keywords from YAML, unioned by `sios_id`.

```
config/          keywords.yaml, collector.yaml
src/sios/        client, parsers, collector CLI, storage
data/raw/        search + detail HTML (gitignored)
data/normalized/ sios.sqlite (gitignored)
tests/fixtures/  saved HTML; tests must not hit live SIOS
docs/            research, collector notes, this handoff
```

CLI (from repo root, venv):

```bash
python -m src.sios.collector --keyword "bóbr" --max-pages 2
python -m src.sios.collector --all-keywords
python -m src.sios.collector --card-id 449913
pytest
```

SQLite: `cards` (PK `sios_id`), `keyword_matches` unique `(sios_id, keyword)`, `collection_runs`. Re-runs update `last_seen_at`, keep `first_seen_at`, merge keywords. Cards are not deleted if they drop out of one query.

## Already implemented

- Technical research of public search (`docs/SIOS_RESEARCH.md`, 2026-10-06).
- Collector: search pagination with duplicate-page stop, detail fetch, raw HTML option, SQLite upsert, structured JSON logs.
- Config-driven keywords and pacing.
- Tests (15 passed last run) for parsers, pagination stop, keyword merge, incremental runs.
- **Pilot only:** `--keyword "bóbr" --max-pages 2` → **60 cards**, 0 errors, SIOS reported **3115** total for that keyword. Not crawled further.
- Local sample data may exist under `data/` (not in git).

Parser notes from the 60-card sample: all had number/year/name/type/case mark/authority/voivodeship; powiat/gmina sometimes empty; 3 public attachment links; related-card links on ~half. Literal values such as `nie dotyczy` are stored as-is. Colspan “Wersja elektroniczna” is handled in the parser; those 60 rows were collected just before that tweak.

## Git

- Repo: `https://github.com/aleksandrahojszyk/sios-monitor.git`
- Branch: `cursor/sios-public-metadata-collector` tracking `origin/cursor/sios-public-metadata-collector`
- HEAD: `3a82bc1` — *Add a paced public SIOS metadata collector with SQLite storage.*
- Remote: up to date as of last `git push`.
- `main` has no separate published history of this work (this branch is the first commit).
- Do not commit `.venv`, raw HTML, or `sios.sqlite`.

Machine note: system Python is **3.7.1**; `pyproject.toml` targets 3.7+ (`httpx>=0.24,<0.25`). SQLite on this Mac is too old for `ON CONFLICT` upsert; storage uses INSERT/UPDATE.

## Known limitations

- `robots.txt` is `User-Agent: *` / `Disallow: /`. Collection is technically possible; large/scheduled crawls need organisational/legal approval. No evasion.
- Rate limits unverified; assume they exist. Keep pacing conservative.
- Keyword search is **not** stemming/synonyms: `bóbr` (3115) ≠ `bobry` (414) ≠ `Castor fiber` (749). Union queries.
- SIOS is a **licensed subset** of Polish authorities, not every environmental case.
- Index is live (`no-store`); pages can shift. Dedup only on `sios_id`.
- HTML scrape will break if markup changes.
- Detail pages include clerk names (RODO).
- Public attachments are recorded as URLs; MVP does not download them during search.
- Do not use `/documents/advancedsearch` (login redirect).

## Do not revisit

- Do **not** rebuild SIOS “API” research unless live behaviour contradicts `SIOS_RESEARCH.md`.
- Do **not** use Playwright for this public GET path.
- Do **not** use card number, title, or case mark as primary key.
- Do **not** treat a single `iid` as national search.
- Do **not** default to undocumented `results=200/500` (UI default 30; 10–100 documented).
- Do **not** stop pagination only on empty pages; detect repeated ID sets.
- Do **not** add frontend, AI classification, Postgres/Supabase, or request-letter workflows until asked.
- Do **not** crawl all ~3115 `bóbr` hits (or `--all-keywords`) without an explicit instruction.
- Do **not** bypass auth, CAPTCHA, or non-public documents.

## Next recommended tasks

1. Confirm approval/pacing before any crawl larger than a small `--max-pages` pilot.
2. If approved: run remaining keyword groups with `--max-pages` caps; union by `sios_id`; compare set overlap (`bóbr` vs `Castor fiber` vs interventions).
3. Optional: export/inspect SQLite (counts, missing location, attachment flags) — still no UI.
4. Optional: download **only** files already linked on public cards (`/documents/download/id/{fileId}`), with the same delay.
5. Later (new phase): case-level grouping (not card-level), classification, information-access request drafts.

Owner: Aleksandra (Designer). Prefer working in code. Commit only when asked.
