# Usability test script

Moderator script for the first Monitoring Inbox test with Nasz Bóbr
volunteers. Read the lines in quotes aloud. Keep the rest as instructions.

Do not help unless the participant is stuck for more than about a minute.
Do not explain the status model in advance. Do not say which cards are
“correct.” Do not mention which EkoKarty rows are synthetic.

Setup: [USABILITY_TEST_SETUP.md](USABILITY_TEST_SETUP.md)  
Notes: [USABILITY_OBSERVATION_TEMPLATE.md](USABILITY_OBSERVATION_TEMPLATE.md)

---

## Before the participant arrives

- [ ] Isolated dataset prepared
- [ ] Reviews reset to NEW
- [ ] Server started with `USABILITY_TEST_MODE=1` and this person’s `PARTICIPANT_ID`
- [ ] Banner shows the participant id and “isolated dataset”
- [ ] Observation template printed or open on a second screen
- [ ] Timer ready (phone is fine)
- [ ] Browser bookmarks: Inbox `http://127.0.0.1:5050/`

Recommended ids: P01, P02, P03.

---

## Introduction (3 minutes)

“Thank you for helping us test this tool. You currently look at public
registers by hand. We built a first version of a Monitoring Inbox that
lists cards we already collected from SIOS and from EkoKarty.

This is not a test of you. We are testing whether the Inbox is
understandable. There are no right answers. Please think out loud if
you can: say what you are looking at and what you would do next.

The statuses you will see are labels we invented. They do not send
anything to an office and they do not create a case file.

I will give you short tasks. You can ask questions. If you get stuck I
will wait a bit, then we will move on.

I will take notes and the computer will record which cards you open and
which labels you choose. We are not recording video unless we agreed
that separately.”

---

## Pre-test questions

Ask these before showing the Inbox. Do not suggest answers.

1. How do you currently monitor new cases?
2. Which registers do you usually check?
3. What information tells you a case is worth attention?
4. What usually takes the most time?

If they mention a typical time for a batch (for example one voivodeship
or one sitting), write that number down. That is the baseline. Do not
ask them to beat it.

---

## Show the Inbox (1 minute)

Open `http://127.0.0.1:5050/`.

“This is the queue. You can scroll, open a card, change a label, write a
note, search, and filter. Please use it as you would if this were your
monitoring shift. Start when you are ready.”

Start the timer for Task 1 when they look at the first row.

---

## Task 1 — Scan new records

“Review the first 10 New cards. For each card, decide what you would
normally do in your current monitoring process.”

Observe, do not prompt:

- whether the user understands the row
- whether they open the detail view
- whether they open the original source
- what information they look for

After the tenth card, stop the timer for this batch.

### After Task 1

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 2 — Ignore irrelevant records

“Find three cards you consider irrelevant and mark them accordingly.”

Check:

- whether IGNORE is understood
- whether disappearing from NEW is expected

If they mark something other than IGNORE, do not correct them. Ask why
after the task.

### After Task 2

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 3 — Reverse a decision

“Change one ignored card back to New.”

Check discoverability and reversibility. If they cannot find ignored
cards, wait, then point at the Status filter only if they are still
stuck.

### After Task 3

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 4 — Relevant vs Monitor

“Find a card that matters but does not require immediate action.”

Observe whether the user chooses RELEVANT or MONITOR.

Ask why. Do not explain the difference first.

If they say the two labels mean the same thing, write that down. Do not
fix it.

### After Task 4

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 5 — Request documents

“Find a card where you would want the full documentation.”

Observe whether REQUEST_DOCUMENTS matches their mental model.

Then ask, without leading:

“What do you think happens when you choose Request documents?”

If they think a letter or ePUAP request is sent, note that as critical.
You may then say: “In this version it only labels the card. Nothing is
sent.”

Explicitly verify that users do not expect this action to automatically
send a request. If they did expect that, record it; do not redesign
during the session.

### After Task 5

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 6 — Find a specific record

“Find a record using either a case reference, authority, keyword, or
location.”

If they need a prompt, offer one real value from the current queue (copy
a case reference or authority from a visible row). Do not invent a query
that you know will fail.

Test search and filters.

### After Task 6

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## Task 7 — Open source

“Open the original public card and then return to the Inbox.”

Check navigation and context loss: new tab, lost filters, lost place in
the list, confusion about which card they had open.

Two EkoKarty fixtures have no public URL. If they land on one of those,
observe what they do. Do not apologise unless they ask.

### After Task 7

- What did you expect to happen?
- Was anything missing?
- Was anything unnecessary?
- Would you normally need to open the original card here?

---

## End-of-session questions

- Which cards were easiest to assess?
- Which were hardest?
- What information would you want visible directly in the Inbox?
- Was the difference between RELEVANT and MONITOR clear?
- What did REQUEST_DOCUMENTS mean to you?
- Would this replace part of your current workflow?
- What would prevent you from using it regularly?

Do not use leading questions. Do not list features we might build.

---

## Close

“Thank you. Your labels will be cleared before the next person. The
notes from this hour are for improving the Inbox, not for scoring the
cards.”

Click **End session**, then export:

```bash
python -m src.inbox.export_usability_session --participant P01
```

Reset before the next volunteer:

```bash
python -m src.inbox.reset_usability_test --participant P02
```
