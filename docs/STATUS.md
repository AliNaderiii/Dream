# Status

Running status of the Dream multi-role build programme. Updated at the end of
every milestone with what shipped, what was measured, what is next, and what
is blocked.

## M3 — Natural Persian dates — SHIPPED

**What shipped.** `dream/reminders.parse_persian_date()` turns the phrases real
people type — «فردا», «پانزدهم مهر», «۱۵ مهر ۱۴۰۴», «اول هر ماه», «سه روز
بعد», «شنبه هفته آینده», «آخر ماه» — into the same midnight timestamps the
scheduler already uses, with the Jalali module as the single source of
calendar truth. Ordinal and colloquial day words (1–31), month names,
relative periods with numbers, weekdays, and every-month day phrases are
covered. Ambiguous input («مهر» without a day, «بیستم» without a month) is
rejected with a worked example, never guessed. `/remind` accepts a natural
date phrase in place of the digit date.

**What was measured.**

- Acceptance table: 26 real phrases with resolved Jalali dates, run at a fixed
  reference instant (1405-05-17 noon) — all 26 correct (pasted in the PR).
- Adversarial pass: Arabic-yeh spellings, ZWNJ vs space, joined vs spaced
  compounds, Persian vs ASCII digits, and «آبان»/«آذر» (alef-madda folding)
  all resolve identically to their canonical forms.
- Impossible dates rejected: «سی و یکم آبان» (Aban has 30 days), Gregorian
  year with a Persian month, unknown phrases — each with a hint.
- Full suite before: `405 passed in 11.59s`; ruff clean.
- Full suite after: `457 passed in 11.92s` (+52); with `-W error`:
  `457 passed in 12.56s`, zero warnings.
- Break-and-restore: with the CLI's natural-date branch disconnected, the 5
  CLI integration tests fail (the parser's 47 unit tests still pass);
  restored, all 52 pass.
- Regression list (13 items): all pass after M3.

**What is next.** M4 — the memory provider interface: the seam that makes
everything after it possible. An abstract provider with a small lifecycle
(available, initialise, contribute to the system prompt, recall before a
turn, persist after a turn, expose tools, shut down); the existing store
becomes the built-in provider with unchanged behaviour; a manager registers
providers and fans calls out, one failing provider never breaking a turn.

**What is blocked.** Nothing.

## M2 — Non-blocking model calls — SHIPPED

**What shipped.** The post-turn extraction pass now runs on a background
worker: a turn waits at most `DREAM_EXTRACTION_TIMEOUT_SECONDS` (default 5.0)
for it, marks the pass `abandoned` with the elapsed budget in the message, and
returns the reply anyway; the worker keeps running and stores facts when the
provider finally answers. HTTP 429 rate limits are retried with exponential
backoff (`DREAM_MAX_RETRIES`, default 3; `DREAM_RETRY_BACKOFF_SECONDS`,
default 1.0); only 429 is retried, a hanging provider is bounded by the
per-request timeout, and an exhausted retry budget reports
«abandoned after N attempts». Extraction never retries: it would stretch its
wall-clock budget.

**What was measured.**

- Pre-M2: instant reply, extraction hanging 8 s → turn wall time `8.00s`
  (all of it the extraction block).
- Post-M2, same scenario, default budget: turn wall time `5.00s`, reply
  instant, `extraction.status == abandoned`, message
  `did not finish within 5.0s`; budget is configurable down to 0.1 s.
- Full suite before: `395 passed in 10.70s`; ruff clean.
- Full suite after: `405 passed in 11.59s` (+10); with `-W error`:
  `405 passed in 11.83s`, zero warnings.
- Break-and-restore: with the bounded join replaced by an unbounded wait
  (the old blocking behaviour), the hanging-extraction and visibility tests
  fail (10 s turn, no abandoned status); restored, all 10 pass.
- Regression list (13 items): all pass after M2.

**What is next.** M3 — natural Persian dates: parse Persian date expressions
(tomorrow, the fifteenth of Mehr, the first of every month) into the
timestamps the scheduler already uses, keeping the Jalali module as the single
source of truth; ambiguous input is rejected with an example.
*(Shipped — see above.)*

**What is blocked.** Nothing.

## M1 — Reminders reach the model — SHIPPED

**What shipped.** The agent turn now searches scheduled reminders with the
user's query, includes anything due soon (overdue, or due within 7 days)
regardless of the query, and renders the chosen reminders into a labelled
Persian section of the system prompt with their stored Jalali dates. The
section shares the existing `DREAM_MEMORY_BLOCK_CHAR_LIMIT` budget and is
fitted *after* memories, so reminders can never crowd memories out; it is
omitted entirely when nothing qualifies, leaving the prompt byte-for-byte as
before. New code: `prompt_reminders()` in `dream/reminders.py` (selection and
ranking) and `Dream._reminder_block()` plus prompt constants in
`dream/agent.py`.

**What was measured.**

- `grep -c -i remind dream/agent.py` → `0` (the measured M1 problem: the model
  never saw reminders).
- Full suite before: `384 passed in 10.65s`; ruff `All checks passed!`.
- Full suite after: `395 passed in 9.89s` (+11 new tests); with `-W error`:
  `395 passed in 9.99s`, zero warnings.
- Acceptance demo (scripted backend, no network): the Persian oil question
  puts the stored date `1405-12-01` and the reminder text in the system
  prompt; a question with no reminder sends no reminder section; a store with
  no reminders adds zero prompt overhead.
- Break-and-restore: with the reminder wiring disconnected, 4 of the new
  integration tests failed (including the oil acceptance test); restored, all
  11 pass.

**What is next.** M2 — non-blocking model calls: extraction must stop blocking
the reply, add retry with backoff on rate limits, and surface a clear message
when a call is abandoned. *(Shipped — see above.)*

**What is blocked.** Nothing.

## M4 — Memory provider interface — SHIPPED

**What shipped.** `dream/providers.py` defines abstract `MemoryProvider`
with lifecycle (available, initialise, recall, list_reminders,
contribute_prompt, persist, expose_tools, shutdown); `BuiltInMemoryProvider`
wraps `MemoryStore`; `ProviderManager` registers providers, fans out
calls, and isolates one failure from a turn. `Dream.__init__` now accepts
either `store` or `manager` (backward-compatible; existing `Dream(store,)
calls unchanged); `Dream.run()` uses `manager.recall()` and
`manager.list_reminders()` and calls `manager.persist()` after the turn.
No mutual dependency: `MemoryStore` stays independent of `providers.py`.

**What is not wired yet.** `contribute_prompt` and `expose_tools` are declared on the interface but the conversation loop does not call them yet. The reason: the prompt path built in M1 was left untouched so it could not regress. Wiring them is the job of the first milestone that needs them.

**What was measured.**

- Before: 457 passed in 13.34s; ruff clean.
- After: 465 passed in 11.98s (+8 new provider tests); with `-W error`:
  465 passed in 12.09s, zero warnings.
- Break-and-restore (manual + `test_break_and_restore_isolation`):
  manager recalls correctly before break; with a broken provider's recall
  replaced by a raiser the manager still returns safely (isolation); after
  restore all 8 provider tests pass.
- Interface isolation verified: broken init (`BrokenInitProvider`) is not
  registered; broken recall does not stop the turn; shutdown completes even
  when providers raise.
- Regression list (12 items): all pass after M4 (24 representative
  regression tests run, 465 total suite).

**What is next.** M5 — Telegram: long polling, no inbound port, pairing
step so strangers cannot read memories, reminders fire into the chat.

**What is blocked.** Nothing.

## Planned milestones

M1 reminders reach the model (shipped) → M2 non-blocking model calls
(shipped) → M3 natural Persian dates (shipped) → M4 memory provider interface
→ M5 Telegram → M6 real tool layer → M7 skills → M8 locale separation → next
three proposed with measurements.
