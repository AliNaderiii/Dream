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
3. call a backend with the generated tool schemas;
4. approve or block each requested tool and append its structured result; and
5. repeat until a textual answer or the iteration limit, then journal the
assistant reply and return an observable `Turn`.

Each `Dream` instance registers `remember_fact`, `search_memory`, and
`forget_memory` functions bound to its own `MemoryStore`.

## Backends

Backends expose `chat(messages, tools) -> {"content", "tool_calls"}`.
`OpenAIBackend` uses `urllib.request` against an OpenAI-compatible endpoint;
`OllamaBackend` selects a local compatible endpoint; and `EchoBackend` provides
deterministic offline time and arithmetic tool calls for tests and demos. The
backend boundary leaves memory files and tool schemas independent of any
particular model vendor.

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
