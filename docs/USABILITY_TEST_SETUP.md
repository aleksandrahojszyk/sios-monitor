# Usability test setup

Prepare the Monitoring Inbox for a structured test with 2–3 Nasz Bóbr
volunteers who currently monitor RDOŚ registers by hand.

This is **not** a product redesign. Do not add Case management, AI,
document-request sending, or login before the test. Do not change the
status model because of a guess. Observe first.

## What this test answers

1. Can users understand a card without opening the source page?
2. Can they decide quickly whether a card is relevant?
3. Do they understand RELEVANT vs MONITOR vs REQUEST_DOCUMENTS?
4. What information is missing from the list or detail view?
5. How often do they need to open the original SIOS/EkoKarty card?
6. How long does it take to triage a batch?
7. Does the Inbox reduce effort compared with manual register browsing?

## Dataset

The test uses an **isolated SQLite file**, not the volunteer collector
database.

| Path | Role |
|---|---|
| `data/normalized/sios.sqlite` | Volunteer/collector DB. Do not use during the test. |
| `data/usability/inbox.sqlite` | Isolated test dataset. |
| `config/usability_dataset.yaml` | Which SIOS cards are copied. |

About **28 cards**: 24 real SIOS rows copied from the local collector
database (identity unchanged) plus 4 EkoKarty Warszawa fixtures.

No live EkoKarty bounded collect was available, so the EkoKarty rows are
**synthetic fixtures**. They are marked in `raw_fields._usability_fixture`
and that marker is hidden in the UI (`_` prefix). Do not tell participants
which rows are synthetic unless they ask.

| EkoKarty identity | Origin |
|---|---|
| `ekokarty:rdos-warszawa:77888` | Research HTML fixture (decision `4365/2026`) |
| `ekokarty:rdos-warszawa:77887` | Research HTML fixture (related application) |
| `ekokarty:rdos-warszawa:usability-waste` | Invented IGNORE-style fixture |
| `ekokarty:rdos-warszawa:usability-nogeo` | Invented missing-location fixture |

The mix includes:

- clearly beaver-related decisions and applications
- weaker or non-beaver titles (possible IGNORE)
- several document types
- `case_reference` on most cards
- missing municipality and missing county
- related cards (pair `439274` / `439276` is both in the set)
- attachment metadata

Do not run a crawl to rebuild this set. If a listed SIOS id is missing
from the local collector DB, prepare will warn and skip it.

## One-time prepare

From the project root, with the virtualenv active:

```bash
python -m src.inbox.prepare_usability_dataset
```

This copies the listed SIOS cards into `data/usability/inbox.sqlite` and
adds the four EkoKarty fixtures. It does not write to
`data/normalized/sios.sqlite`.

Re-running prepare refreshes copied card metadata. It does not delete
event logs unless you remove the usability SQLite file.

## Start a session

One participant at a time. Review statuses are shared inside the test
database.

```bash
USABILITY_TEST_MODE=1 PARTICIPANT_ID=P01 python -m src.inbox.app
```

Open [http://127.0.0.1:5050/](http://127.0.0.1:5050/).

A banner shows the participant id. The queue, statuses, filters, search,
notes, and “Open original card” behaviour are the same as the Inbox MVP.

`USABILITY_TEST_MODE=1` will refuse to open the volunteer database.

## During the session

Follow [USABILITY_TEST_SCRIPT.md](USABILITY_TEST_SCRIPT.md).

Record notes in
[USABILITY_OBSERVATION_TEMPLATE.md](USABILITY_OBSERVATION_TEMPLATE.md).

The app logs, with timestamps:

- session start / end
- card viewed
- original source opened
- status change (previous and new)
- note added

Participant id is `PARTICIPANT_ID`. There is no login.

Use **End session** on the banner when the interview is finished, or stop
the process. Either way, export afterwards.

## Reset between participants

```bash
python -m src.inbox.reset_usability_test --participant P02
```

This command:

- sets every test review back to NEW (deletes `card_reviews` in the usability DB)
- closes open usability sessions
- keeps collector card rows
- keeps `review_events` so P01’s log remains
- refuses to run against `data/normalized/sios.sqlite`

Then start the next person:

```bash
USABILITY_TEST_MODE=1 PARTICIPANT_ID=P02 python -m src.inbox.app
```

## Export results

```bash
python -m src.inbox.export_usability_session --participant P01
```

Writes:

- `data/usability/P01_events.csv`
- `data/usability/P01_summary.csv`

The summary is a spreadsheet, not a dashboard. Derived columns include
cards viewed, source-page opens, cards viewed without opening source,
status counts, reversals, seconds to view 10 cards, and average seconds
per viewed card.

Do not treat those times as a success target. Measure the actual baseline
first, including how long the volunteer’s current register workflow takes
(ask in the pre-test questions).

Omit `--participant` to export every participant in the test database.

## Success criteria (promising, not pass/fail)

The first test is promising if:

- users can review most cards without moderator help
- users understand IGNORE
- users understand REQUEST_DOCUMENTS does not send anything
- users can find the original source
- users can reverse statuses
- users can search/filter successfully
- most relevant cards can be assessed without opening the source page
- review time per card is materially lower than the current manual workflow

Do not hardcode a target review time yet.

## Hypothesis to observe, not fix

RELEVANT and MONITOR may not be distinct for volunteers. If participants
repeatedly treat them as the same thing, record that as a product-model
issue. Do not change the status model during or immediately after the
first sessions.

## What was not added

No Case entity, no AI, no document-request generation, no authentication,
no collector changes, no Inbox redesign.

## Blockers before real volunteers

- Confirm `data/usability/inbox.sqlite` exists (`prepare_usability_dataset`).
- Confirm the volunteer DB is **not** the file being opened (banner must say
  “isolated dataset”).
- Confirm SIOS “Open original card” links still resolve on the public site.
- The two invented EkoKarty cards have no public URL (“Open original card
  unavailable”). That is intentional.
- Research-based EkoKarty URLs (`77888`, `77887`) may open a live public
  page; if the live card has moved, note it as a trust/source issue.
- Run the session on the moderator’s machine or a dedicated laptop. There
  is no remote login and no hosted environment.
- Budget extra time for a Polish-language conversation even though the UI
  is currently English.
- Do not collect SIOS/EkoKarty during the session.
