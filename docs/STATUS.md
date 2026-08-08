# Status

Running status of the Dream multi-role build programme. Updated at the end of
every milestone with what shipped, what was measured, what is next, and what
is blocked.

## M10 — Teaching the model when a procedure is a skill, not a fact — SHIPPED

**What shipped.** The M4 `contribute_prompt` hook, declared and never called
since M4, is wired for the first time: the skills subsystem supplies its own
usage line (`SKILLS_USAGE` in `dream/skills.py`) through a new
`SkillPromptProvider` that `Dream` registers beside the built-in memory
provider, and the conversation loop appends the provider block to the system
prompt after the memory-usage instructions. The model is finally told, in
Persian, that a step-by-step procedure (the owner says «یاد بگیر» or
«اول... بعد...») is a method, not a fact about the user — not to be stored in
memories; to gather every step and save it once with `save_skill`, never one
skill per message, re-saving under the same name when later steps arrive; and
to look procedures up with `use_skill` when the user asks how to do
something, answering normally when nothing matches. `remember_fact` stays for
durable facts. No store, scheduler, calendar, extraction, Telegram, CLI, or
tool-module change.

**Multi-message decision, stated and defended.** The model gathers the whole
procedure across messages and saves once per message that adds steps, always
under the same name — M9 already defines overwrite-under-the-same-name as the
correction path, so a later step extends the one file instead of creating a
second skill. The owner's two-message transcript therefore ends in exactly one
skill of three steps, and at no point do two skills exist. A clarifying
question was rejected: the transcript has no confirmation turn, and
per-message skills are exactly the measured failure.

**The hook answer, in one sentence.** We wire the M4 `contribute_prompt` hook
and let the skills subsystem supply its own prompt line, rather than
hardcoding a second mechanism in the conversation module.

**What was measured** (scripted backend — no live model answered:
`OPENAI_API_KEY` unset, no Ollama in the environment; the scripted
`PromptFollowingBackend` uses a tool only when the system prompt names it,
the measured M9 principle, so the before/after tool choice is driven by the
prompt text).

- Full suite before: `536 passed`; ruff `All checks passed!`; with
  `-W error::DeprecationWarning`: `536 passed`.
- Full suite after: `543 passed` (+7); ruff `All checks passed!`; with
  `-W error::DeprecationWarning`: `543 passed`; the new tests raise no
  `ResourceWarning` under `-W error::ResourceWarning`.
- The owner's two-message transcript, replayed on unchanged source (red
  before any implementation): `remember_fact` per message, `[memory] stored
  2 facts` then `[memory] stored 1 fact`, **3 rows, 0 skills** — the measured
  M9 numbers reproduced exactly. After: `save_skill` per message, one skill
  «تمدید بیمه ماشین» of three steps (file printed in the PR), **memory rows
  3 → 1**; the model writes zero rows, the single remaining row is the
  unchanged extraction pass's durable-fact output («کاربر در حال تمدید بیمه
  ماشین است»), which this milestone was forbidden to touch.
- A fact-shaped statement («اسم کامل من سارا رادمنش است») still becomes a
  memory row via `remember_fact` and creates no skill file.
- A how-to request («چطور بیمه ماشین را تمدید کنم؟») causes a `use_skill`
  call whose result carries the stored steps and the reply repeats them; an
  unrelated request («قیمت دلار امروز چقدر است؟») causes no tool call at
  all. The scoping mechanism is the instruction text itself: `use_skill` is
  tied to how-to requests and the prompt tells the model to answer normally
  when nothing matches; both directions are measured above.
- The skills line reaches the system prompt of a real turn and the provider
  honours its char budget (block omitted when it would not fit, leaving the
  prompt byte-for-byte as before).
- Break-and-restore: every new test was observed red against a deliberate
  one-line break and green again after `git checkout`; the two
  still-works pins (fact routing, unrelated-turn silence) are insensitive to
  every M10 source line by design, so their red was demonstrated by breaking
  the pinned routing in the model stand-in. Messages are in the PR.
- Standing regression list (20 items, 72 nodes): all pass.

**On scope.** The milestone measures 466 new lines against the ~400 advisory
budget; the excess sits in the mandated Persian escape constants and the
scripted-backend battery. The natural split point, had it been needed, is the
test file (~364 lines: the prompt-following backend, the Persian constants,
and the seven tests); the source change itself is ~100 lines.

**What is next.** Skills on the phone: the Telegram command list deliberately
has no skill commands until the terminal shape has proven itself; the M4
`expose_tools` hook remains declared and unwired. Windows reserved device
names: a skill named for a console device is accepted today and lands inside
the workspace, so nothing escapes, but the file may be unwritable on the
owner's machine — one line, next milestone.

**What is blocked.** Web search remains procurement, not engineering:
key-free endpoints return empty pages for the owner's real queries.

## M9 — File-backed skills — SHIPPED

**What shipped.** A skill is a durable procedure: a UTF-8 text file in
`skills/` under the workspace root with three labelled parts — `name:`,
`description:` (when it applies), and `steps:` — which the owner can open,
correct by hand and have the correction take effect on the next use; nothing
is cached, nothing is rebuilt, and the store gains no table. New module
`dream/skills.py` owns parsing, writing (through the existing `_safe_path`
boundary, with skill names shaped like paths refused), and matching; the tool
module exposes `save_skill` (guarded), `use_skill` and `list_skills` (safe);
the terminal gains `/skill QUERY` and `/skills`. Matching reuses
`normalize_fa`, the suffix stemmer and the synonym index — no third
mechanism — scoring skill-side content-stem coverage against the
synonym-expanded query, with two guards: at least a third of the skill's
stems covered, and two shared stems unless coverage is full. Broken files
(missing parts, invalid UTF-8, oversized) are skipped and reported; an empty
directory is not an error. A skill naming a dangerous tool changes nothing
about that tool's approval.

**Measured during the adversarial pass.** The suffix stemmer is not
transitive across inflections («دوست» stems to دوس but «دوستش» to دوست;
«بنویسم» to بنویس but «بنویسد» stays — د is not a suffix), so exact-set
intersection misses real paraphrases; matching therefore counts two stems as
equal when one prefixes the other with a three-letter floor (two-letter «دم»
must never claim «دما»). «درست» and «درس» conflate to one stem — safe only
because both sides are stemmed and the two-shared-stems guard absorbs it.

**What was measured.**

- The cross-session test was written against unchanged source and observed
  red (`unknown tool: save_skill`) before any implementation.
- Full suite before: `521 passed in 13.91s`; ruff `All checks passed!`.
- Full suite after: `536 passed in 12.96s` (+15); with
  `-W error::DeprecationWarning`: `536 passed in 13.44s`; new tests raise no
  `ResourceWarning` under `-W error::ResourceWarning`.
- Printed evidence (in the PR): a real skill file, the same file after a hand
  edit with the edited step returned on next use, reuse across two separate
  store and conversation instances, three Persian phrasings finding one skill
  plus an unrelated dollar-price query finding nothing, three refused names
  with their error payloads, and broken files listed as problems while the
  good skill keeps answering.
- Near-miss pair («پیامک تبریک تولد» vs «پیامک تبریک سال نو»): each request
  routes to its own skill and the wrong skill does not clear the bar
  (measured coverages 0.60/0.67 vs 0.20/0.25; multi-word scaffold paraphrases
  with no shared content return zero).
- Break-and-restore: every new test was observed failing against a
  deliberate one-line source break and green again after `git checkout`;
  two initial breaks that silently exercised nothing (a cache that was never
  primed, a gate opened on a branch the dangerous path never reaches) were
  caught, the test or the break was corrected, and the red was observed.
  Messages are in the PR.
- Standing regression list (19 items, 63 nodes): all pass.

**On scope.** The milestone measures ~960 new lines against the ~800
advisory budget; the excess sits in the mandated Persian adversarial battery
and the per-test break-and-restore evidence. The natural split point, had it
been needed, was the two CLI commands (~60 lines with their test); the
remainder is one inseparable seam.

**What is next.** Surface relevant skills in the system prompt (the
`contribute_prompt` hook still declared and unwired) once the terminal shape
has proven itself, then Telegram.

**What is blocked.** Web search remains procurement, not engineering:
key-free endpoints return empty pages for the owner's real queries.

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

## M5 — Secure local Telegram front end — SHIPPED

**What shipped.** Secure Telegram long polling, pairing, refusal handling, and
reminder delivery into paired chats. Pairing and token-redaction review remains
unchanged.

**What was measured.** 490 tests pass after M5. Two M6 concurrency defects were
then reproduced: the first consumer consumed reminders globally, and deferred
transactions raised `database is locked` under a two-process barrier.

## M6 — Per-destination reminder delivery and atomic due checks — SHIPPED

**What shipped.** Due checks now use `BEGIN IMMEDIATE`, and delivery state is
stored in idempotently-created `reminder_deliveries` plus destination first-seen
state. Each caller supplies a destination identity; the terminal remains the
`terminal` default and Telegram uses each paired chat identity. A destination
first seen later receives the current occurrence, not historical pile-up. A
reminder advances once per due occurrence, while each destination receives it
once; one-offs remain available to later destinations. Existing repeat, anchor,
pile-up, clock, and single-terminal behavior are preserved.

**What was measured.** Two real-process barrier tests and two-destination
regressions cover the findings; full suite and ruff are recorded in the PR.
The delivery table upgrades old databases with data intact. The interface hooks
`contribute_prompt` and `expose_tools` remain unwired and carried forward.

**Known and deferred.** Provider 429 payloads are still too verbose for Telegram;
raw tool results can still be embedded in Persian replies; and family names can
be dropped during extraction. These remain deferred to a later milestone.

## M6C — Tests for per-destination delivery — SHIPPED

**What shipped.** Tests only; no source changed. Two new files pin the M6
delivery rule that shipped with no coverage: `tests/test_reminder_delivery.py`
(six delivery and migration tests) and `tests/test_concurrent_processes.py`
(the real-process barrier test). They assert that two destinations each receive
the same due reminder exactly once; that a one-off still reaches a second
destination after the first consumed it and the row went inactive (the defect
M6 existed to fix); that a repeating reminder advances exactly one period no
matter how many destinations read it; that the default destination behaves as
before for a lone terminal; that a database from the previous release opens,
gains the two delivery tables, and keeps its data; and that thirty
barrier-synchronised two-process due checks are never refused.

**What was measured.**

- Full suite before: `490 passed`; ruff `All checks passed!`.
- Full suite after: `497 passed` (+7); under `-W error::DeprecationWarning`:
  `497 passed`.
- The seven new tests raise no `ResourceWarning` of their own under
  `-W error::ResourceWarning` (every process and connection is closed).
- Thirty-trial real-process barrier: `0` of 30 refused (reverting the atomic
  transaction to a deferred read-before-write made it 30 of 30 raise
  `database is locked`).
- Break-and-restore: each new test was seen red against a one-line source
  break and green after `git checkout` restored it; messages are in the PR.
- Regression list (13 items): all pass after M6C.

**On the never-seen-destination behaviour.** A destination the store has never
seen receives every currently-overdue reminder in one batch, but only when it
first checks at the same instant those reminders fired (`last_fired_at >=
first_seen` with both equal to `now`). Replay to a newly arrived destination is
reasonable; the timing coupling is not — a destination added a moment later
sees nothing. That deserves its own milestone rather than a change here.

**Known and deferred.** The three defects carried over from M6 (verbose 429
payloads, raw tool results in Persian replies, dropped family names) are
untouched and still deferred.

## M8 — Example decontamination, extraction guard, mobile forget — SHIPPED

**What shipped.** Three coordinated changes eliminate the invented-biography
hazard and allow phone-based memory management. Worked examples in the
extraction prompt were rewritten with generic, non-owner topics (astronomy with
a Dobsonian telescope, Sara Radmanesh family-name preservation, oil painting
fan brush, pottery workshop) so no worked example can be mistaken for the
owner's real biography. A grounding guard in `extract_facts` verifies that
candidate facts share substantive subject-matter stems or synonyms with the
user message, discarding prompt echoes and ungrounded hallucinations. The
Telegram front end allow list now includes `/forget`, giving the owner
phone-level capability to archive false memories with explicit numeric ID
validation and mistap safety.

**What was measured.**

- Legitimate facts count before and after: `10/10` legitimate test facts
  preserved across categories (names, tools, domains, episodic events,
  preferences, and code expressions).
- Prompt echoes rejected: `6/6` prompt echo candidates rejected across diverse
  user inputs (e.g. `اسم کامل من علیرضا نادری است.` rejecting `کاربر روی استارتاپ فین‌تک کار می‌کند`).
- Persian work question: asking «کجا کار می‌کنم؟» when no work memory is
  stored produces an admission of lack of knowledge rather than inventing
  technical consulting or fintech startups.
- Telegram `/forget`: verified archiving an active memory via chat ID,
  rejecting invalid non-numeric IDs, rejecting non-existent IDs, and leaving
  memories intact on a zero-argument mistap.
- Full suite before: `509 passed in 15.04s`; ruff `All checks passed!`.
- Full suite after: `521 passed in 13.31s` (+12); with
  `-W error::DeprecationWarning`: `521 passed in 13.70s`, zero warnings.
- Break-and-restore: observed failures on disconnected guard, missing
  family-name prompt example, and omitted `/forget` command; restored from
  version control and confirmed green.
- Standing regression list (17 items): all 17 items ran and passed.

**What is next.** Define the first-seen destination semantics deliberately;
M6C still pins the timing-coupled behavior without blessing it.

**What is blocked.** Nothing.

## M7 — Failure replies, clock shape, full-name extraction — SHIPPED

**What shipped.** Three independent rough edges were removed. Provider request
failures now keep full redacted diagnostics on the terminal while the chat reply
is one short Persian sentence, with distinct wording for rate limits, network
unreachability, rejected requests, and unexpected failures. The clock tool no
longer returns ISO 8601 to the conversation; it returns a Persian Jalali date
and local time rendering, so a Persian reminder answer cannot accidentally
start with a machine timestamp or timezone offset. The extraction prompt now
tells the extractor to preserve the owner's exact name wording and includes a
worked example with a family name.

**What was measured.**

- Baseline before source changes: `497 passed in 13.29s`.
- Full suite after: `509 passed in 13.86s`; ruff over the repository:
  `All checks passed!`; with `-W error::DeprecationWarning`:
  `509 passed in 12.92s`.
- Provider failure wall: four stubbed failures were measured. Each raw error
  remained on the terminal diagnostic line with credentials absent; each chat
  reply was the intended short Persian sentence.
- Clock shape: the tool wrapper now returns `status=ok` with a Jalali/Persian
  rendering. A scripted Persian oil-reminder reply contained the stored
  `1405-12-01` date and no ISO timestamp, no timezone offset, and no Latin
  month name.
- Full-name extraction: no live provider was configured (`OPENAI_API_KEY` was
  unset), so the ten-trial measurement used a prompt-sensitive scripted
  backend. Before the prompt change the family name survived `0/10`; after the
  change it survived `10/10`.
- Regression list: 52 targeted regression tests passed, including the two
  per-destination delivery tests added in M6C.

**Effect on the open unknown-answer hazard.** These changes should not make the
assistant more likely to bluff. Provider failures are now explicit failures
rather than raw payloads, and the extraction change asks for exact preservation
of what the owner said instead of paraphrasing. The broader confident-unknown
problem remains open outside reminders.

**What is next.** Define the first-seen destination semantics deliberately;
M6C still pins the current timing-coupled behaviour without blessing it.

**What is blocked.** Nothing.

## Planned milestones

M10 teaching skill-vs-fact via the wired `contribute_prompt` hook (shipped)
→ Telegram skill access → web search once the owner supplies a key or a relay
→ locale separation.
