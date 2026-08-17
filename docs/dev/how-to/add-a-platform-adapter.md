# How to add a platform adapter (connectivity)

A platform adapter lets Dream bridge into a messaging service (Telegram,
Discord, Slack, WhatsApp, Signal, Email are the six shipped).

## The connectivity pattern

1. **Adapter** (`dream/connectivity/adapters/<name>.py`) — the transport that
   sends/receives messages for one platform. It subscribes to a gateway
   interface, not the other way around.
2. **Gateway** (`dream/gateway_server.py`) — the shared hub that owns the web
   gateway, token management, and the message log. Adapters register with it.
3. **Bridge** (`dream/bridge/methods.py`) — the `gateway.*` RPC methods the UI
   calls to configure, start, stop, and read logs.
4. **Frontend** (`apps/desktop/src/routes/connectivity.tsx` +
   `src/components/connectivity/`) — the platform card, config form, and log.

## Steps

1. Create the adapter file with the same shape as an existing one (e.g.
   `telegram.py`): `configure()`, `start()`, `stop()`, and a message callback.
2. Register it in the gateway's platform registry so it shows up in
   `gateway.list_platforms`.
3. Add the platform name to `GatewayPlatformName` in
   `apps/desktop/src/lib/bridge/types.ts`.
4. Add a `PlatformCard` entry and config field definitions in
   `apps/desktop/src/components/connectivity/config-fields.ts`.
5. Add i18n keys (all eight locales) for the platform's label and any new
   strings.
6. Test with an echo transport (see `src/lib/bridge/echo-gateway.ts`) — never
   hit a live service from tests.

## Conventions

- Secrets (bot tokens) go through `keyring`, never into config files.
- Every adapter must degrade gracefully when its platform is unreachable.
