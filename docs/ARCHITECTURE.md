# Architecture

Dream has four small layers: durable memory, a registry of typed tools, a
provider-neutral model interface, and the agent loop that joins them.

## Memory

`MemoryStore` is a SQLite database with an FTS5 index. A memory is one of:

- **semantic** — stable facts and preferences;
- **episodic** — events tied to time; or
- **procedural** — instructions and learned rules.

Content and tags are passed through `normalize_fa` when written and every query
is normalised before retrieval. Persian letter-form and digit variants therefore
share an index representation.

Search starts with FTS5 terms and a small Persian suffix stemmer, then scores
candidate memories as:

```text
0.55 * relevance + 0.20 * recency + 0.15 * importance + 0.10 * usage
```

Similarity/relevance alone is insufficient for personal memory. A precise match
from years ago should not always displace a current preference; importance lets
the owner preserve consequential facts; and usage gives repeatedly useful facts
a modest boost. Recency uses a 30-day half-life. The journal is separate from
distilled memories, so raw conversation is not silently promoted to fact.

## Tools and safety

`@tool` reads a callable's type hints and docstring parameter descriptions to
construct one JSON Schema. `REGISTRY` stores the callable, schema, description,
and real risk tier. OpenAI and Anthropic schema adapters are views of that same
registry.

- `safe`: read-only; automatically allowed.
- `guarded`: local reversible writes; automatically allowed and logged.
- `dangerous`: external or irreversible effects; requires explicit approval.

`ApprovalPolicy` obtains the tier from `REGISTRY`, never from model-supplied
arguments. With no approval callback, dangerous actions fail closed. The agent
consults the policy before it calls `execute`; a blocked request is returned to
the model as structured data so it can explain the refusal.

## Agent turn

A `Dream.run()` turn performs the following work:

1. append the user's message to the journal;
2. retrieve relevant memories and place them in a labelled private section of
the Persian system prompt, with relative ages;
3. select scheduled reminders — those relevant to the query plus anything due
soon — and render them in their own labelled section between the usage
instructions and the memory section, each with its stored Jalali date;
4. call a backend with the generated tool schemas;
5. approve or block each requested tool and append its structured result; and
6. repeat until a textual answer or the iteration limit, then journal the
assistant reply and return an observable `Turn`.

## Reminders in the prompt

Reminders reach the model the same way memories do: `prompt_reminders()` in
`dream/reminders.py` scores each active reminder by query relevance (the
fraction of its own normalised, stemmed tokens that appear in the query) plus
an urgency bonus (overdue 1.0, due within the 7-day window 0.5). A reminder
qualifies when relevance is non-zero *or* the urgency bonus is non-zero, so
something due surfaces even when the turn's wording shares no tokens with it,
while the far-future schedule stays out unless the turn concerns it. At most
five lines reach the prompt.

The reminder section shares the memory block's character budget
(`DREAM_MEMORY_BLOCK_CHAR_LIMIT`). Memories are fitted to the budget first;
the reminder section gets only what remains, so reminders can never crowd
memories out. When nothing qualifies or nothing fits, the section is omitted
and the prompt is byte-for-byte what it was before this feature.

## Natural Persian dates

`parse_persian_date()` in `dream/reminders.py` resolves the phrases real
people type — «فردا», «پانزدهم مهر», «۱۵ مهر ۱۴۰۴», «اول هر ماه», «سه روز
بعد», «شنبه هفته آینده» — into the same midnight timestamps the scheduler
already uses. It is a pure phrase interpreter: all calendar math stays in
`dream/jalali.py`, the single source of truth. Words are matched
space-insensitively after `normalize_fa`, so joined, ZWNJ, and spaced
spellings are the same day; Arabic-yeh and alef-madda spellings fold onto the
Persian forms. Ambiguous input — a month without a day, a day without a
month — raises `ValueError` with a worked example; it is never guessed.
`/remind` accepts a natural phrase in its date slot via prefix matching: the
longest leading phrase that parses becomes the date, everything after is the
reminder text and repeat spec.

Each `Dream` instance registers `remember_fact`, `search_memory`, and
`forget_memory` functions bound to its own `MemoryStore`.

## Backends

Backends expose `chat(messages, tools) -> {"content", "tool_calls"}`.
`OpenAIBackend` uses `urllib.request` against an OpenAI-compatible endpoint;
`OllamaBackend` selects a local compatible endpoint; and `EchoBackend` provides
deterministic offline time and arithmetic tool calls for tests and demos. The
backend boundary leaves memory files and tool schemas independent of any
particular model vendor.

A call that answers with HTTP 429 is retried with exponential backoff
(`DREAM_MAX_RETRIES`, `DREAM_RETRY_BACKOFF_SECONDS`): a rate-limited provider
is alive and may recover. No other status is retried — a 400 is a rejection,
a hang is bounded by the per-request timeout — and a call that burns its
retries reports «abandoned after N attempts» instead of looking like an
ordinary failure.

## Extraction runs in the background

After the reply loop finishes, a daemon worker thread runs the extraction pass
and stores any facts it finds. The turn waits at most
`DREAM_EXTRACTION_TIMEOUT_SECONDS` (default 5.0) for the worker: a fast pass
reports its facts on the turn exactly as before, while a provider that hangs
leaves the turn marked `abandoned` and the reply goes out anyway — the worker
keeps running and stores the facts when the provider finally answers. The
extraction backend is the conversation backend at a colder temperature with
retries disabled, so the pass never retries into its own wall-clock budget.
Every exception inside the worker is contained and reported on the turn, never
escaped into the reply path.

A tool call crosses that boundary in two shapes. Inside Dream it is the flat
`{"id", "name", "arguments": {...}}` mapping that the approval policy and
`execute` consume. On the wire it must be `{"id", "type": "function",
"function": {"name", "arguments": "<json string>"}}`, so the agent converts
each call before appending it to conversation history; history is replayed
verbatim on every later request, and a flat call there is rejected with HTTP
400 from the second turn onwards.

When a request fails, the backend reports the server's response body alongside
the status code, because `HTTP Error 400: Bad Request` alone never names the
field that was rejected. Bodies are whitespace-collapsed and truncated, and the
configured API key and any bearer token are redacted before the text is shown.
