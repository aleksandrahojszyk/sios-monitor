# Usability observation template

One copy per participant. Fill during the session. Do not score the
volunteer. Severity describes the product issue, not the person.

Participant: ______________  
Date: ______________  
Moderator: ______________  
`PARTICIPANT_ID`: ______________  
Baseline time they reported for current monitoring: ______________

---

## Task log

| Task | Observation | User quote | Severity | Evidence | Possible interpretation |
|---|---|---|---|---|---|
| 1 Scan first 10 New cards |  |  |  |  |  |
| 2 Ignore three irrelevant cards |  |  |  |  |  |
| 3 Change one ignored card back to New |  |  |  |  |  |
| 4 Card that matters but no immediate action |  |  |  |  |  |
| 5 Card where they want full documentation |  |  |  |  |  |
| 6 Find a record (search / filter) |  |  |  |  |  |
| 7 Open original public card and return |  |  |  |  |  |

Severity options:

- **Critical** — cannot complete the task, or believes the tool sent a
  request / created a case / changed a public register
- **High** — completes the task only with help, or systematically
  misreads identity, source, or status
- **Medium** — hesitation, extra steps, or missing information that
  slowed the decision
- **Low** — preference, wording, or polish

Evidence examples: timestamp, card number, `external_key`, filter used,
whether the source page was opened, export row from
`data/usability/P0X_events.csv`.

---

## Timed notes (Task 1)

Time to review 10 cards: ______________  
Opened detail (count): ______________  
Opened original source (count): ______________  
Assessed from the list only (count): ______________

---

## Pre-test answers

How do you currently monitor new cases?

Which registers do you usually check?

What information tells you a case is worth attention?

What usually takes the most time?

---

## Status-model notes (do not fix during the test)

Chose RELEVANT when the prompt was “matters but no immediate action”: yes / no

Chose MONITOR for that prompt: yes / no

Treated RELEVANT and MONITOR as the same: yes / no / unclear

Thought REQUEST_DOCUMENTS sends a request: yes / no

Found IGNORE and expected the card to leave New: yes / no / did not notice

Reversed a status without help: yes / no

---

## Information gaps

_What they looked for and could not find in the list or detail._

-

## Navigation issues

_Lost place, lost filters, new-tab confusion, back-to-inbox problems._

-

## Status-model confusion

_NEW / RELEVANT / IGNORE / MONITOR / REQUEST_DOCUMENTS._

If RELEVANT and MONITOR are not meaningfully distinct, record that here
as a product-model issue. Do not change the statuses in this round.

-

## Trust / source-transparency issues

_Did they know the source was SIOS vs EkoKarty? Did the original page
match what the Inbox showed? Did synthetic or missing URLs break trust?_

-

## Missing metadata

_Location, municipality, county, attachments, related cards, dates,
authority, case reference, document type._

-

## Workflow expectations

_What they thought the Inbox would do next: send a request, create a
case, alert a lawyer, remember a person, sync with a spreadsheet._

-

## Feature requests

_Capture what they asked for. Do not promise it._

-

## Do not build yet

Use this list to keep the first test from turning into a roadmap. Move
an item out of this list only after the sessions are done and the
evidence is reviewed.

Examples that stay here unless evidence is overwhelming:

- Case entity / clustering related cards into one case
- AI summaries or relevance scores
- Automatic document-request letters or ePUAP
- Login / user accounts
- Notifications, email, or scheduling
- Downloading attachments
- Changing RELEVANT vs MONITOR before seeing whether volunteers
  distinguish them
- Extra filters “because we might need them”
- Polish UI translation driven only by the moderator, not by
  participants

Participant asked for (park here):

-
