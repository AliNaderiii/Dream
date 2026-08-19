# Connectivity Architecture — Multi-Platform Gateway (P-07)

> Status: **implemented** · Prompt P-07 (Phase 3.1–3.6) · One agent, one memory,
> every channel.

## 1. Mission

Dream lives on the desktop. The connectivity gateway gives it six more front
doors — Telegram, Discord, Slack, WhatsApp, Signal, and Email — while keeping
**one brain**: every inbound message is normalised into an
`IncomingMessage`, routed through the existing `dream.agent.Dream` loop, and
answered with the agent's reply split to the platform's length limit. All six
surfaces share the same durable `MemoryStore`, the same skills, tools, and
approval policy. This is the Hermes-Agent "many front-doors, one brain"
pattern.

## 2. Package layout

```
dream/connectivity/
├── models.py        # IncomingMessage, Attachment, PlatformStatus, log entries
├── base.py          # PlatformAdapter ABC + split_text()
├── ratelimit.py     # {platform, user_id, minute} gate counter
├── config.py        # per-platform JSON config + secret redaction
├── platforms.py     # static catalog of the six platforms (fields, capabilities)
├── auth.py          # single-use link codes + linked-user registry
├── sessions.py      # (platform, user_id) → Dream, persisted index
├── messagelog.py    # per-platform ring buffer (JSONL), content-stripped for e2e
├── websocket.py     # minimal RFC 6455 client (Discord gateway + Slack Socket Mode)
├── gateway.py       # orchestrator: loop thread, router, lifecycle, status
└── adapters/
    ├── telegram.py  # long-polling getUpdates (urllib)
    ├── discord.py   # gateway WS + REST, Deferred interactions, threads, uploads
    ├── slack.py     # Socket Mode, envelope acks, response_url replies
    ├── whatsapp.py  # Cloud API webhook server (ThreadingHTTPServer) + sender
    ├── signal.py    # signal-cli receive/send, fail-fast binary check
    └── email.py     # IMAP IDLE + poll fallback, MIME parse, SMTP threads
```

Everything is Python standard library only (`urllib`, `http.server`,
`imaplib`/`smtplib`/`email`, `asyncio`, `subprocess`, plus the local RFC 6455
client). `pyproject.toml` gains no dependencies.

## 3. Threading model

```
┌────────────────────── bridge process (python -m dream.bridge) ─────────────────────┐
│                                                                                     │
│  bridge asyncio loop        gateway event-loop thread (dream-connectivity)          │
│  ┌──────────────────┐       ┌──────────────────────────────────────────────┐        │
│  │ BridgeMethods    │──────▶│ Gateway                                      │        │
│  │ gateway.*        │ submit│  ┌──────────┐ ┌───────────┐ ┌─────────────┐ │        │
│  │ handlers         │_async │  │ adapters │ │ sessions  │ │ message log │ │        │
│  └──────────────────┘       │  │ (6)      │ │ per (p,u) │ │ ring buffer │ │        │
│                             │  └────┬─────┘ └───────────┘ └─────────────┘ │        │
│                             │       │ route_message: log → auth → rate →  │        │
│                             │       │ command → Dream.run → split → send  │        │
│                             │       │                                     │        │
│                             │  WhatsApp webhook HTTP thread ──┐           │        │
│                             │  run_coroutine_threadsafe ──────▶│           │        │
│                             └──────────────────────────────────┴──────────┘        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

* The **gateway owns its own `asyncio` event-loop thread**, independent of the
  bridge loop. Adapter websockets and the webhook server stay alive between
  RPC calls. `Gateway.start_loop()` / `stop_loop()` manage the thread;
  `submit(coro)` / `submit_async(coro)` ferry work across with
  `run_coroutine_threadsafe`.
* Adapter coroutines run **on the gateway loop**. The bridge awaits them via
  `submit_async` — it never calls `.result()` on the bridge loop.
* The blocking Dream turn runs with `asyncio.to_thread`, so a minute-long
  model call never stalls other channels.
* The WhatsApp webhook handler thread pushes deliveries onto the gateway loop
  with `run_coroutine_threadsafe`.

## 4. Adapter contract

```python
class PlatformAdapter(ABC):
    platform_name: ClassVar[str]
    max_message_length: ClassVar[int]
    supports_inline: ClassVar[bool]
    supports_attachments: ClassVar[bool]
    privacy: ClassVar[str]            # "plaintext" | "e2e"

    async def start(self) -> None
    async def stop(self) -> None
    async def send_message(self, user_id, text, attachments=None) -> None
    async def send_typing_indicator(self, user_id) -> None
```

Adapters receive their incoming-message callback through the constructor
(`on_message`) and have **no back-reference to the Gateway**. Each adapter has
a pluggable transport seam (`TelegramTransport`, `DiscordHttp` +
`ws_connect`, `SlackApi` + `ws_connect`, `WhatsAppApi` + webhook server,
`SignalCli`, `ImapClient`/`SmtpClient`) so every platform is unit-tested with
an injected fake — no network in the test suite.

| Platform | Transport | Inbound | Outbound | Limit |
| --- | --- | --- | --- | --- |
| Telegram | long-poll `getUpdates` (urllib) | text updates | `sendMessage` | 4096 |
| Discord | gateway WS + REST | MESSAGE_CREATE, INTERACTION_CREATE | REST / Deferred+`PATCH @original` | 2000 |
| Slack | Socket Mode WS | `events_api`, `slash_commands` (always acked) | `chat.postMessage` / `response_url` | 4000 |
| WhatsApp | webhook `ThreadingHTTPServer` | GET verify + POST messages (optional HMAC) | `POST /messages` | 4096 |
| Signal | `signal-cli receive --json` | dataMessage envelopes | `send --message-from-stdin` | 4096 |
| Email | IMAP IDLE (raw-socket trick) + poll fallback | MIME parse, HTML→text | SMTP with `In-Reply-To`/`References` | 4000 |

## 5. The routing pipeline

Every message, from every surface, passes through the same gates
(`Gateway.route_message`, gate G4):

1. **Log** inbound (text is stored empty for `privacy == "e2e"` platforms).
2. **Pre-auth commands.** `/link <code>`, `/help`, `/start` work before
   linking — `/link` is how a chat gets in.
3. **Auth.** When the platform requires it (`require_auth`, default on),
   unlinked chats receive the refusal text.
4. **Rate limit.** Fixed-minute window over `{platform, user_id, minute}`;
   default 20/min, configurable per platform via `rate_limit_per_minute`.
5. **Commands.** `/help`, `/status`, `/new_session`, `/link <code>`.
6. **Agent.** Best-effort typing indicator, then one
   `asyncio.to_thread(Dream.run, text)` on the channel's own Dream instance.
7. **Split & send.** `split_text()` breaks the reply at word boundaries to
   the platform's `max_message_length`, each chunk is sent and the outbound
   side is logged.

## 6. Sessions, auth, and state

* **Sessions** — `SessionRegistry` maps `(platform, user_id)` to one Dream
  instance, so history is per-channel and stable across messages (gate G5).
  `/new_session` resets a channel. The metadata index persists as JSON;
  agent history itself is in-memory, mirroring the bridge session index.
* **Auth** — the desktop issues a 6-digit link code (`gateway.link_code`,
  single-use, 10-minute TTL, constant-time comparison). The human sends
  `/link CODE` from the chat; the redeemed identity is persisted in the
  linked-user registry (`gateway.linked_users`, `gateway.unlink_user`).
* **Rate limiter** — buckets keyed by `{platform, user_id, minute}`; old
  buckets are pruned on window roll-over, so counters never grow unbounded.
* **Message log** — a per-platform `deque(maxlen=100)` persisted as JSONL,
  newest-first via `gateway.logs`. **Signal (e2e) rows store empty text in
  both directions** — the log records that a message happened, never its
  content (gate G11).

## 7. Configuration and secret handling

`data/connectivity.json` holds per-platform configs, written atomically with
0600 permissions. The catalog in `dream/connectivity/platforms.py` declares
each platform's fields and which are required and secret. Every public read
path — `gateway.status`, `gateway.platforms`, `gateway.configure` replies —
passes through `redact_config()`, which masks values whose key name contains
`token`, `secret`, `password`, `key`, or `credential`. A blank secret in a
configure call keeps the previously stored value ("leave unchanged"), so the
UI never needs to echo a secret back.

## 8. Bridge integration

Nine RPC methods (documented in `docs/bridge/protocol.md` §3.11):

`gateway.start`, `gateway.stop`, `gateway.status`, `gateway.configure`,
`gateway.logs`, `gateway.link_code`, `gateway.linked_users`,
`gateway.unlink_user`, `gateway.platforms`.

`BridgeMethods` builds the gateway lazily on first use (config path from
`DREAM_CONNECTIVITY_PATH`, default `data/connectivity.json`), passes the
bridge's `dream_factory` so connectivity sessions use the same provider
configuration as desktop sessions, and tears the loop down in `aclose()`.

## 9. Security posture (gate G11)

* Link-code pairing before anything else; codes single-use and time-bounded.
* Secrets never cross the bridge: config replies are redacted, and the
  redaction rule applies to any key name marking a secret.
* Signal is end-to-end encrypted by design; the gateway additionally strips
  its content from the message log.
* Email skips messages from our own address and tracks already-replied
  Message-IDs, so reply loops cannot form.
* WhatsApp webhook bodies are bounded, GET verification is constant-time, and
  an optional app secret enables HMAC-SHA256 signature validation.
* Adapter failures are quarantined in the per-adapter status — one platform
  misbehaving never takes down the gateway or the bridge.

## 10. Testing

`tests/test_connectivity_*.py` (55 tests, all `asyncio`-based, no third-party
packages):

* `models` / `ratelimit` / `sessions` — value types, window arithmetic,
  persistence;
* `gateway` — a fake adapter + fake Dream drive the full pipeline: link-code
  flow, refusal, rate limit, commands, split-to-limit, session reuse,
  log redaction for e2e;
* `websocket` — frame round-trips against a local asyncio RFC 6455 server
  (text/JSON, ping→pong, fragmentation, 64-bit lengths, close handshake,
  refused upgrades);
* `adapters` — one test per platform with an injected fake transport;
* `bridge` — the `gateway.*` RPC surface through `BridgeMethods`, including
  shutdown of the gateway loop.

Frontend: Vitest covers the echo gateway runtime, the pure config-field
helpers, the Zustand store, and the Connectivity route (catalog render,
start/stop, configure save, secret reveal, e2e log notice).

## 11. Reference implementation map

| Concern | Python | TypeScript |
| --- | --- | --- |
| Gateway + router | `dream/connectivity/gateway.py` | `lib/bridge/echo-gateway.ts` (echo) |
| Adapter contract | `dream/connectivity/base.py` | — |
| Platform catalog | `dream/connectivity/platforms.py` | `lib/bridge/echo-gateway.ts` |
| RPC surface | `dream/bridge/methods.py` §gateway | `lib/bridge/types.ts`, `routes/connectivity.tsx` |
| Screen + store | — | `routes/connectivity.tsx`, `stores/use-connectivity-store.ts` |
| WebSocket client | `dream/connectivity/websocket.py` | — |

## 12. S03 Telegram Live hardening

S03 keeps the two existing Telegram entry points but aligns their security and
phone behavior:

* **Standalone `dream-telegram`.** `TELEGRAM_BOT_TOKEN` is read only from the
  environment. With `TELEGRAM_ALLOWED_USER` set, that numeric Telegram user is
  the sole owner and pairing is disabled. Without it, startup prints one
  six-digit code valid for ten minutes; the code works once, only in a private
  chat, and the paired chat is persisted. Every other identity and every group
  chat is refused before commands, reminders, memory, or the model can run.
* **Connectivity Telegram adapter.** Desktop `/link CODE` uses the same visible
  security properties: six digits, ten-minute TTL, one successful redemption,
  persistent linked identity. Telegram updates are accepted only from private
  chats. The long-poll offset advances only after the gateway handler returns
  successfully, so a transient route failure retries rather than silently
  dropping an update.
* **Phone command parity.** Telegram gateway commands delegate to
  `cli.dispatch_command` behind `cli.PHONE_COMMANDS`. This single source makes
  `/plan`, `/usage`, and `/route` available on both Telegram entry points, and
  `/help` renders the allowlisted phone surface. A slash command not in that
  policy receives the standard refusal and is never treated as a model prompt.
  The S00 commerce kernel is present, so these commands are read-only status
  surfaces; S03 adds no purchase or payment flow.
* **Long replies.** Standalone replies and due reminders are split into chunks
  no longer than 4,000 characters. Pending delivery stores the first unsent
  chunk; after a mid-message transport error, already delivered chunks are not
  repeated and the update offset remains unacknowledged until all chunks send.
* **Credential boundaries.** Telegram-token, Bearer, common API-key, labelled
  credential, environment credential, and configured secret values are
  sanitised before transport errors, adapter status, gateway logging, and
  plaintext JSONL message persistence. Tracebacks carrying raw exception text
  are not logged at the gateway boundary. Public configuration still uses the
  existing key-based redaction.
* **Dangerous tools.** Telegram sessions construct `ApprovalPolicy` without an
  approver. Model-requested dangerous tools therefore return
  `dangerous tool denied: no approver configured`; they are not executed. A
  phone command cannot bypass this because non-allowlisted slash commands are
  refused before model dispatch.

All Telegram tests inject fake transports. CI neither needs nor accepts a live
BotFather token; the owner-only live procedure is in `docs/handoff/S03.md`.
