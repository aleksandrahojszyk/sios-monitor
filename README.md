# SIOS monitor

Minimal collector of **public** SIOS information-card metadata
([https://system.sios.pl/search/common](https://system.sios.pl/search/common)).

This project does not include a frontend, classification, or document-request workflows.

Technical background: [docs/SIOS_RESEARCH.md](docs/SIOS_RESEARCH.md)  
Operational constraints: [docs/COLLECTOR_NOTES.md](docs/COLLECTOR_NOTES.md)

## Setup

Python 3.7+

```bash
cd sios-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

- `config/keywords.yaml` — independent search queries (unioned by numeric SIOS ID)
- `config/collector.yaml` — delay, timeout, page size, raw HTML, SQLite path

Default delay is **1.5 seconds** between HTTP requests. Do not lower this for large runs without approval.

Default page size is **30** (the documented public UI default).

## Run the collector

From the project root:

```bash
python -m src.sios.collector --keyword "bóbr"
python -m src.sios.collector --keyword "Castor fiber" --max-pages 5
python -m src.sios.collector --all-keywords
python -m src.sios.collector --card-id 449913
```

Useful flags:

- `--max-pages N` — hard cap on search pages
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

## Data

| Path | Contents |
|---|---|
| `data/raw/search/` | Search HTML (`search_bobr_page_1.html`, …) |
| `data/raw/details/` | Card HTML (`449913.html`, …) |
| `data/normalized/sios.sqlite` | Tables `cards`, `keyword_matches`, `collection_runs` |

Primary key is **numeric SIOS ID** (`/documents/details/id/{id}`). Card numbers such as `2047/2026` are not unique.

## Tests

```bash
pytest
```

Tests use saved HTML fixtures only. They do not call live SIOS.

## Do not do yet

Do not run a full nationwide crawl of thousands of cards unless it is explicitly requested. `robots.txt` disallows `/`; see collector notes.
