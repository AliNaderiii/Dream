# Frontend bridge client

The React side talks to the sidecar through a typed client in
`apps/desktop/src/lib/bridge/client.ts`. Components never touch raw IPC;
they call typed wrappers.

## The client

- `getBridgeClient()` — the singleton JSON-RPC client.
- `client.call<T>(method, params)` — a request/response call.
- `client.stream(method, params)` — a streaming subscription.

## Typed wrappers

Each domain has a wrapper module that maps RPC results to typed DTOs and
centralises error handling:

| Module | Covers |
| --- | --- |
| `lib/bridge/memory.ts` | `memory.*` |
| `lib/bridge/skills.ts` | `skill.*` |
| `lib/bridge/data-science.ts` | `data.*` / `notebook.*` |
| `lib/bridge/hooks.ts` | the `useBridge()` hook |

DTOs live in `lib/bridge/types.ts` and mirror the sidecar's JSON shapes.

## Echo transports

For browser-only development (no sidecar), each domain ships a deterministic
echo runtime — e.g. `lib/bridge/echo-data.ts` seeds a 1,000-row dataset, and
`lib/bridge/echo-subagents.ts` simulates subagents. `npm run dev` uses them so
every screen is browsable without Python.

## Usage in a component

```ts
const { client } = useBridge();
const page = await listMemories(client, { limit: 25 });
```

The hook yields a `client` bound to the native bridge when running in Tauri and
to the echo transports otherwise.
