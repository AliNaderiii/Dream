# Dream — Python API reference

The Python core is the agent, memory, tools, and skills. Public entry points
are re-exported from `dream/__init__.py`.

## Top-level

- `Dream` — the agent. Construct with a backend and a memory store; call it
  with a user message to run a turn.
- `Turn` — one completed turn: `reply`, `tool_calls`, `memories_used`,
  `memories_created`, `elapsed_seconds`.
- `ApprovalPolicy` — risk-tier rules; `.allows(tool_name, arguments)` →
  `(allowed, reason)`.
- `Memory` / `MemoryStore` — durable, Persian-normalised SQLite/FTS5 memory.
- `build_backend` — resolve a backend name to a backend instance.

## Backends

- `OpenAIBackend` — any OpenAI-compatible endpoint.
- `OllamaBackend` — a local Ollama server.
- `EchoBackend` — offline deterministic backend for demos/tests.

## Tools

- `tool(*, risk="safe")` — decorator that registers a function and derives its
  JSON Schema from the signature/docstring.
- `REGISTRY` — name → `Tool` (name, function, description, schema, risk).
- `execute(name, **args)` — run a registered tool; returns
  `{"status": "ok", "result": …}` or a structured error.
- `openai_schemas()` / `anthropic_schemas()` — schema views per wire format.

## Extraction

- `extract_facts` / `ExtractionResult` / `ExtractedFact` — the memory-extraction
  pass that runs after each turn.

## Normalisation

- `normalize_fa` — Persian spelling/digit normalisation used on write and read.

## Modules

| Module | Responsibility |
| --- | --- |
| `dream.agent` | agent loop, backends, approval |
| `dream.memory` | SQLite/FTS5 store, retrieval |
| `dream.tools` | tool registry + risk tiers |
| `dream.skills.data_science` | sandboxed data pipeline |
| `dream.skills.notebooks` | Jupyter integration |
| `dream.provenance` | append-only SHA-256-chained log |
| `dream.mcp` / `dream.acp` | Model Context Protocol / Agent Client Protocol |
| `dream.connectivity` | platform adapters |
| `dream.bridge` | the JSON-RPC sidecar |

> The JSON-RPC surface is documented separately in
> [`docs/bridge/protocol.md`](../../bridge/protocol.md) §3; the mapping from
> method name to implementation lives in its §9.
