# SIOS monitor

Minimal collector of **public** SIOS information-card metadata
([https://system.sios.pl/search/common](https://system.sios.pl/search/common)).

The first user-facing surface is the **Monitoring Inbox**, a triage queue over
already collected SIOS and EkoKarty metadata. It is not a case-management
system and it does not crawl public websites.

Technical background: [docs/SIOS_RESEARCH.md](docs/SIOS_RESEARCH.md)  
EkoKarty research: [docs/EKOKARTY_RESEARCH.md](docs/EKOKARTY_RESEARCH.md)  
Source coverage draft: [docs/SOURCE_COVERAGE_DRAFT.md](docs/SOURCE_COVERAGE_DRAFT.md)  
Operational constraints: [docs/COLLECTOR_NOTES.md](docs/COLLECTOR_NOTES.md)  
Inbox MVP: [docs/MONITORING_INBOX_MVP.md](docs/MONITORING_INBOX_MVP.md)

## Setup

Python 3.7+

```bash
cd sios-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

- `config/keywords.yaml` — independent SIOS search queries (unioned by numeric SIOS ID)
- `config/collector.yaml` — delay, timeout, page size, raw HTML, SQLite path
- `config/sources.yaml` — the 16 enabled voivodeship search scopes
- `config/ekokarty.yaml` — EkoKarty delay, result cap, SQLite path
- `config/ekokarty_sources.yaml` — verified EkoKarty institutions (`rdos-warszawa` only)
- `config/ekokarty_keywords.yaml` — EkoKarty-specific keyword groups

Default delay is **1.5 seconds** between HTTP requests. Do not lower this for large runs without approval.

Default page size is **30** (the documented public UI default).

## Run the collector

From the project root:

```bash
python -m src.sios.collector --keyword "bóbr"
python -m src.sios.collector --keyword "bóbr" --source dolnoslaskie --max-pages 3
python -m src.sios.collector --keyword "Castor fiber" --max-pages 5
python -m src.sios.collector --all-keywords
python -m src.sios.collector --card-id 449913
python -m src.sios.collector --keyword "bóbr" \
  --source dolnoslaskie --since 2026-08-06 --until 2026-10-06 --max-pages 20
python -m src.sios.collector --keyword "bóbr" \
  --source dolnoslaskie --incremental --max-pages 10
```

Useful flags:

- `--max-pages N` — hard cap on search pages
- `--source KEY` — use one source from `config/sources.yaml`
- `--since YYYY-MM-DD` — inclusive bounded collection using SIOS `entered_at`
- `--until YYYY-MM-DD` — inclusive end date; defaults to today with `--since`
- `--incremental` — derive the window from the last safe bounded run
- `--delay 2.0` — seconds between requests
- `--no-raw` — skip saving HTML snapshots
- `--log-level DEBUG`

Example output:

```
Keyword: bóbr
Pages processed: 7
Unique cards found: 350
New cards: 42
Existing cards: 308
Errors: 0
```

Repeated runs update `last_seen_at` and merge keyword matches. They do not insert duplicate `sios_id` rows.

### Province-first monitoring

The primary monitoring unit is a voivodeship. Every configured province source
uses:

```
iid=0
id_provinces=<1..16>
```

`id_provinces` is geographic scope. `iid` is institution scope; the two are not
equivalent. Province monitoring intentionally includes cards from every
publishing authority represented in that geography, including RDOŚ, Wody
Polskie, starostwa, municipalities, and other public bodies. The parsed
`authority` value is stored exactly as SIOS provides it and is not inferred
from the source.

The source key records which province search discovered a card. Card identity
is separate: SIOS cards use `("sios", str(sios_id))`. `record_sources` retains
all province-source relationships, so keyword overlap, province overlap, and
repeated runs do not duplicate the card.

Running without `--source` preserves the existing nationwide/manual behavior.

### EkoKarty (RDOŚ Warszawa only)

EkoKarty is a second public-data source, not a nationwide index and not a
replacement for `mazowieckie` SIOS monitoring. The adapter is institution-scoped
and currently enables only `rdos-warszawa`.

```bash
python -m src.ekokarty.collector --keyword "Castor fiber" \
  --institution rdos-warszawa --since 2026-01-01 --until 2026-01-31
python -m src.ekokarty.collector --all-keywords \
  --institution rdos-warszawa --since 2026-01-01 --until 2026-01-31
python -m src.ekokarty.collector --keyword "bobry" \
  --institution rdos-warszawa --incremental
```

Identity is `("ekokarty", "{slug}:{card_id}")`, for example
`ekokarty:rdos-warszawa:77888`. Card numbers, related-card URL segments, and
case references are stored but are not unique keys. SIOS and EkoKarty rows are
never merged because their fields look similar.

Listing search is HTTP POST with `karty_all` plus `data_od` / `data_do`. A
2000-row response is a cap, not a complete result set: the collector splits
the listing-date window and logs every split. `--since` or `--incremental` is
required so an uncapped POST cannot be treated as complete.

- `config/ekokarty_sources.yaml` — verified institutions; only `rdos-warszawa` is enabled
- `config/ekokarty_keywords.yaml` — EkoKarty-specific keyword groups
- `config/ekokarty.yaml` — delay, result cap, SQLite path (same database as SIOS)

### Date-bounded collection

The public result-list date is incomplete and corresponds to the document's
received date. Bounded collection instead uses detail-page `Data wprowadzenia`
(`entered_at`), which was present and newest-first across the validated
300-card sample.

Known cards use their stored `entered_at` and do not trigger another detail
request. New cards are fetched as needed. The collector stops after a complete
page is older than `--since`. It validates that `entered_at` remains
non-increasing and stops with `ORDERING_UNSAFE` if the undocumented ordering
assumption fails; it does not silently continue into a historical crawl.

Keep an explicit `--max-pages` safety cap for live bounded runs.

### Incremental monitoring

`--incremental` uses the `window_end` of the latest successful, completely
traversed bounded run for the same source and keyword. It subtracts one day
for overlap and uses today as the new end date:

```
window_start = previous window_end - 1 day
window_end = today
```

This watermark model automatically expands after missed weeks. It does not
fall back to a fixed seven-day window. Known overlap cards use their stored
`entered_at`, so they do not trigger detail requests or duplicate card rows.

Failed, partial, `MAX_PAGES`, `HTTP_ERROR`, and `ORDERING_UNSAFE` runs never
advance the watermark. If no safe prior bounded run exists, automatic mode
refuses to guess and requires an explicit `--since`. Supplying `--since` takes
precedence over `--incremental`.

A successful `dolnoslaskie` run never advances `pomorskie`; nationwide/manual
runs use a separate NULL source scope. Establish each province with one
explicit two-month bounded backfill before its first incremental run.

## Monitoring Inbox

After collectors have written to the local SQLite file:

```bash
python -m src.inbox.app
```

Open [http://127.0.0.1:5050/](http://127.0.0.1:5050/). The Inbox reads
`data/normalized/sios.sqlite` only. Default view is unreviewed (`NEW`) cards.
Review status and notes are stored in `card_reviews`, not in collector fields.

### Usability test (isolated)

Do not use the volunteer database for volunteer interviews. Prepare the
isolated set, then start the Inbox with a participant id:

```bash
python -m src.inbox.prepare_usability_dataset
USABILITY_TEST_MODE=1 PARTICIPANT_ID=P01 python -m src.inbox.app
python -m src.inbox.export_usability_session --participant P01
python -m src.inbox.reset_usability_test --participant P02
```

Setup, script, and observation sheet:

- [docs/USABILITY_TEST_SETUP.md](docs/USABILITY_TEST_SETUP.md)
- [docs/USABILITY_TEST_SCRIPT.md](docs/USABILITY_TEST_SCRIPT.md)
- [docs/USABILITY_OBSERVATION_TEMPLATE.md](docs/USABILITY_OBSERVATION_TEMPLATE.md)

## Data

| Path | Contents |
|---|---|
| `data/raw/search/` | SIOS search HTML (`search_bobr_page_1.html`, …) |
| `data/raw/details/` | SIOS card HTML (`449913.html`, …) |
| `data/raw/ekokarty/` | EkoKarty listing and detail HTML |
| `data/normalized/sios.sqlite` | Tables `cards`, `record_sources`, `keyword_matches`, `collection_runs` |

Record identity is `(source_system, native_record_id)`. SIOS uses
`("sios", str(sios_id))`. EkoKarty uses `("ekokarty", "{slug}:{card_id}")`.
Card numbers such as `2047/2026` are not unique.

## Tests

```bash
pytest
```

Tests use saved HTML fixtures and in-memory/temp SQLite only. They do not call live SIOS or EkoKarty. The Inbox tests never start a crawl.

## Do not do yet

Do not run a full nationwide crawl of thousands of cards unless it is explicitly requested. SIOS `robots.txt` disallows `/`; see collector notes. Do not enable other EkoKarty institutions or build a nationwide EkoKarty crawler.
