# Bridge RPC — method reference

The sidecar is a JSON-RPC 2.0 server over stdio. Framing, the envelope, errors,
and streaming are specified in `docs/bridge/protocol.md`; this page is the
complete method reference (mirroring its §9 implementation map).

## Families

| Prefix | Purpose |
| --- | --- |
| `session.*` | conversation sessions |
| `conversation.*` | talking to the agent (send / stop / stream) |
| `provider.*` | model providers + credentials (keychain) |
| `memory.*` | durable memory (list / count / create / update / delete) |
| `skill.*` | skills (list / get / install / export / enable / delete) |
| `tool.*` | the tool registry (list / schema / call) |
| `approval.*` | human-in-the-loop approval |
| `subagent.*` | isolated background agents (spawn / list / logs / control) |
| `schedule.*` | cron + natural-language schedules |
| `gateway.*` | multi-platform connectivity |
| `data.*` | data-science pipeline (load / profile / clean / analyse / chart / report) |
| `notebook.*` | Jupyter integration |
| `health.check` / `sidecar.version` | liveness + version |

## Envelope

Request:

```json
{ "jsonrpc": "2.0", "id": 1, "method": "memory.list", "params": { "limit": 25 } }
```

Response:

```json
{ "jsonrpc": "2.0", "id": 1, "result": { "memories": [], "total": 0 } }
```

Error:

```json
{ "jsonrpc": "2.0", "id": 1, "error": { "code": -32602, "message": "…" } }
```

## Errors

Domain errors map to standard codes (`INVALID_PARAMS -32602`, `NOT_FOUND
-32601`, plus app-specific codes such as `-32012` for missing Jupyter). See
`docs/bridge/protocol.md` §4.

## Implementation map

`dream/bridge/methods.py` holds `BridgeMethods`, whose methods are registered
by prefix. `docs/bridge/protocol.md` §9 maps each method to its implementation
and the DTO types in `apps/desktop/src/lib/bridge/types.ts`.
