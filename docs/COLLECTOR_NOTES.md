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

## Personal data

Detail pages include clerk names (`Informacje wprowadził/a`). Treat the SQLite file
as containing personal data under RODO and restrict access accordingly.
