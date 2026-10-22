# Collector notes

This collector reads **public SIOS information-card metadata** that is already exposed
without login at [https://system.sios.pl/search/common](https://system.sios.pl/search/common)
and [https://system.sios.pl/documents/details/id/{id}](https://system.sios.pl/documents/details/id/449913).

It does not log in, does not solve CAPTCHAs, does not rotate IP addresses, and does not
use browser automation.

## robots.txt

Verified on 2026-10-06:

```
User-Agent: *
Disallow: /
```

The public site asks automated agents not to crawl. This application still talks to
public HTML URLs because the organisational goal is monitoring of **already published**
environmental information cards. That does **not** cancel the robots restriction.

Before any large-scale or scheduled collection:

1. Obtain production / legal / organisational approval.
2. Keep request pacing conservative (default 1.5s; configurable, not zero).
3. Prefer small `--max-pages` pilots over full result sets.
4. Identify the client with a clear User-Agent (`config/collector.yaml`).
5. Be prepared to **stop or slow down** immediately if SIOS operators object or if
   HTTP 429/503 responses appear.

There is **no** evasion: no proxy pools, no User-Agent rotation, no CAPTCHA bypass,
no use of authenticated endpoints such as `/documents/advancedsearch`.

## Public metadata only

Collected by default:

- Search-result rows (IDs, card numbers, truncated titles, locations)
- Detail-page labelled fields
- Links to public attachments **when the card HTML already lists them**

Not collected in this phase:

- Files that are not linked on the public card
- Logged-in document stores
- Case-management or e-delivery systems

A public “Wersja elektroniczna” file is recorded as a URL in `raw_fields`. The MVP
does not download those files during search collection.

## Request pacing

Rate limits were **not verified** in the research pass. Defaults assume they may exist:

- `request_delay_seconds: 1.5`
- retries with exponential backoff on 408/429/5xx and network errors
- documented UI page size `results=30` (not undocumented 200/500)

Override delay with `--delay` or `config/collector.yaml`. Reducing delay for volume
crawling requires the approval noted above.

## Stopping collection

- CLI: do not start `--all-keywords` or omit `--max-pages` until approved
- Config: raise `request_delay_seconds`, lower `max_pages`
- Process: interrupt the CLI; SQLite writes are per card

Cards are never deleted because they disappear from one keyword result.

## Province source scope

The production monitoring registry is `config/sources.yaml`. Its 16 primary
sources correspond to the 16 voivodeships and send `iid=0` together with the
province's `id_provinces` value.

- `id_provinces` limits card geography.
- `iid` limits an institution/tenant.

These filters are not interchangeable. A province search can and intentionally
does include multiple publishers. For example, the verified dolnośląskie
sample included both RDOŚ Wrocław and Starostwo Powiatowe w Kłodzku. Do not
filter these results to RDOŚ: authority is stored from the card exactly as
published so downstream work can separately identify RDOŚ, Wody Polskie,
starostwa, municipalities, and other authorities.

`collection_runs.source_key` records the search scope. `record_sources` records
every province source through which a SIOS card was discovered. This provenance
is separate from both record identity (`sios` + native numeric ID as text) and
the card's legal publisher.

The public EkoKarty register for RDOŚ Warszawa is documented in
[EKOKARTY_RESEARCH.md](EKOKARTY_RESEARCH.md). It is a separate institution-scoped
HTML source, not a nationwide SIOS equivalent. It does not replace the
`mazowieckie` SIOS province source. The bounded adapter collects only
`rdos-warszawa` (`python -m src.ekokarty.collector`). Other EkoKarty institutions
can be added later through `config/ekokarty_sources.yaml`; do not enable them
without a verified slug. The 16-RDOŚ coverage draft is
[SOURCE_COVERAGE_DRAFT.md](SOURCE_COVERAGE_DRAFT.md).

EkoKarty listing is one HTML POST per filter. There is no `page=` walk. Broad
queries can return exactly 2000 rows; that is a cap. Bounded collection uses
`data_od` / `data_do` against listing date (`Data zamieszczenie w wykazie` /
listing `Data karty`). If a window returns `result_cap` rows, the collector
splits the window, logs `ekokarty_window_split`, and continues. A single-day
window that is still capped is stored as `RESULT_CAP` and does **not** advance
the incremental watermark. Do not treat 2000 rows as a complete dataset.

EkoKarty identity is `("ekokarty", "{slug}:{card_id}")`. Do not deduplicate
against SIOS because card numbers, case marks, or titles look similar. Related
card links and `znak sprawy` are stored as signals, not as a case model.
Attachment URLs are recorded; files are not downloaded.

## Date-bounded runs

Use `--since YYYY-MM-DD` and optionally `--until YYYY-MM-DD` for a capped
recent-period collection. Both boundaries are inclusive.

The date basis is the public card's `Data wprowadzenia` (`entered_at`), not the
collector's `first_seen_at` / `last_seen_at`. In the validated 300-card `bóbr`
sample:

- `entered_at` was present on 300/300 cards and strictly newest-first;
- `published_at` was complete but had 31 adjacent ordering inversions;
- the result-list date was present on 183/300 cards and matched
  `received_at`, not publication/entry time.

SIOS does not document default ordering as a contract. A bounded run therefore
checks `entered_at` ordering while traversing. It stops with `WINDOW_PASSED`
after a complete page is older than the start date. Missing dates or an
ordering increase stop the run with `ORDERING_UNSAFE`; the collector does not
fall back to an unbounded historical crawl.

Known cards with a stored `entered_at` are not detail-fetched again. Continue
to use `--max-pages` as a separate operational safety cap.

## Incremental watermark

After a successful bounded baseline, use `--incremental` for subsequent runs.
The watermark is the `window_end` of the latest safe, successful bounded run
for the same source key and keyword. The collector subtracts one day for
overlap and defaults the new end to today.

Only `ok` runs ending with `WINDOW_PASSED`, `EMPTY_PAGE`, `REPEATED_PAGE`, or
`NO_NEW_IDS` are eligible watermarks. Failed/partial runs and safety-cap stops
do not advance it. If no eligible run exists, the collector requires an
explicit `--since` rather than assuming seven days.

Run metadata records whether the window was `AUTOMATIC` or `EXPLICIT`, the
watermark used, and the overlap days. Explicit `--since` always wins when both
it and `--incremental` are supplied.

Watermarks are deliberately isolated by source. A completed run for one
voivodeship cannot advance another voivodeship, and a legacy/manual nationwide
run cannot seed a province watermark. Each province therefore needs its own
explicit bounded baseline before automatic incremental collection.

EkoKarty watermarks use the same `collection_runs` table and the same one-day
overlap, keyed by institution `source_key` (for example `rdos-warszawa`) and
keyword. Eligible EkoKarty stop reasons are `WINDOW_COMPLETE` and
`EMPTY_WINDOW`. `RESULT_CAP` and `MAX_REQUESTS` never advance the watermark.
The date basis is listing date, not SIOS `entered_at`.

## Monitoring Inbox

The Inbox (`python -m src.inbox.app`) is a local review UI over this SQLite
file. It must not call SIOS or EkoKarty. Human review state lives in
`card_reviews` / `review_events`. See [MONITORING_INBOX_MVP.md](MONITORING_INBOX_MVP.md).

## Personal data

Detail pages include clerk names (`Informacje wprowadził/a`). Treat the SQLite file
as containing personal data under RODO and restrict access accordingly.
