# Monitoring Inbox MVP

## Product purpose

The Monitoring Inbox is a triage queue for volunteers at Nasz Bóbr.

Collectors already store public SIOS and EkoKarty card metadata in the local
SQLite database. The Inbox is the first user-facing place to review those
records, decide whether they matter, and mark a next action.

It is **not** an administrative-case system. **Card ≠ Case.** Reviewing a card
does not create a case, cluster related cards, or request documents.

The Inbox reads only local storage. It never crawls SIOS or EkoKarty.

## User workflow

```text
collector discovers card
        ↓
card appears in Monitoring Inbox as NEW
        ↓
volunteer scans the queue
        ↓
volunteer marks Relevant / Ignore / Monitor / Request documents
        ↓
optional note
        ↓
Open original card (public source URL)
```

Review state persists between sessions in `card_reviews`, separately from
scraped metadata.

## Review statuses

| Status | Meaning |
|---|---|
| `NEW` | Collected, not yet reviewed. Default. |
| `RELEVANT` | Relevant to Nasz Bóbr; no specific next action yet. |
| `IGNORE` | Not relevant to this monitoring workflow. |
| `MONITOR` | Relevant, no immediate intervention. |
| `REQUEST_DOCUMENTS` | Should later enter a document-request workflow. |

`REQUEST_DOCUMENTS` does **not** create a Case entity. Status changes are
reversible and do not alter source metadata.

## Data model

Collected cards remain in `cards` / `keyword_matches` as produced by the SIOS
and EkoKarty collectors.

Human workflow tables:

### `card_reviews`

- `id`
- `source_system` + `native_record_id` (existing namespaced identity)
- `external_key` (canonical key already used by collectors)
- `status`
- `note`
- `reviewed_at`
- `created_at`
- `updated_at`

No foreign key onto `cards`, so a review row can exist even if source metadata
is incomplete.

Identity examples already used in code:

- `sios:449913`
- `ekokarty:rdos-warszawa:77888`

### `review_events`

Lightweight product log: `card_viewed`, `status_changed` (previous and new
status), `note_updated`, plus timestamp. No external analytics service.

`review_events` has no user-account field; review actions are not attributed.

### `users` and `card_claims`

Individual accounts and task ownership, separate from triage:

- `users`: unique `username` and unique `display_name` (case-insensitive),
  salted password hash, `is_active`. Accounts are created by a team
  administrator with `python -m src.inbox.users create`; there is no
  self-registration.
- `card_claims`: primary key `(source_system, native_record_id)`, so a card has
  at most one assignee. A claim is a single `INSERT OR IGNORE`; of two
  simultaneous claims SQLite lets exactly one succeed and the loser is told who
  holds the card. Release deletes the row only when it belongs to the caller.

Claims never touch `card_reviews`, the review status, or the default `NEW`
queue. Sign-in is required to claim or release; reading the Inbox and changing
review status behave as before. Claiming is hidden in isolated usability-test
mode.

## Unified card read model

`InboxRepository` joins collected cards with reviews for display.

| Field | SIOS | EkoKarty |
|---|---|---|
| source / external_key | `sios:<id>` | `ekokarty:<slug>:<card_id>` |
| card number, type, name, authority, case reference | stored | stored |
| display date | `entered_at` (date part), fallback `published_at` | `listing_date` |
| voivodeship / county / municipality | parsed from `location` | not structured; location shown as free text |
| keywords | `keyword_matches` | `keyword_matches` |
| related cards / attachments | counts from `_related_cards` / `_attachments` | same, when present |
| source URL | public SIOS detail URL | public EkoKarty detail URL |
| review status / note | `card_reviews`, default NEW | same |

Missing optional fields render as unavailable. They are not errors.

**Display date:** newest-first sorting and the date filter use a per-source
field. SIOS `entered_at` is the collector’s window basis (`Data wprowadzenia`).
EkoKarty `listing_date` is `Data zamieszczenie w wykazie`. These are **not**
treated as the same event. The UI labels the field name next to the date.

SIOS and EkoKarty records are never merged because titles, card numbers, or
case marks look similar. One source record = one Inbox row.

## Filters and search

Server-side only (default page size 50):

- review status (default: New)
- source
- authority
- document type
- matched keyword
- date range on the display date above
- voivodeship and county (SIOS structured location only)
- text search over card number, case reference, document name, authority, location

Geography filters do not apply to EkoKarty free-text areas.

## Out of scope

- Card → Case clustering or a Case entity
- AI classification or risk scoring
- Art. 56 analysis
- automatic document requests, e-Doręczenia, deadlines, appeals
- GIS / parcels
- volunteer assignment and complex permissions
- source-coverage UI
- live scraping from the Inbox

## Known limitations

- Local development data may contain only SIOS cards until an EkoKarty run is
  performed. The read model and tests already include both sources.
- EkoKarty geography is unstructured.
- Display dates are source-specific and should not be graphed as one timeline
  without a later mapping.
- One note per card; no note history.
- Reading the Inbox and changing review status do not require sign-in; only
  claim/release uses the signed-in account, and review actions are still not
  attributed to a user.
- Attachment rows are metadata only; files are not fetched.

## Future extension points

- Case entity created explicitly from `REQUEST_DOCUMENTS`
- optional corroboration of SIOS ↔ EkoKarty on authority + znak sprawy, still
  keeping namespaced IDs
- attribute review actions to the signed-in user
- saved views
- richer related-card navigation that still is not a case model
