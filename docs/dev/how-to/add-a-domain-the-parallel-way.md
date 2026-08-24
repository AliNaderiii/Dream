# Add a domain the parallel way

P0 lets a feature ship as new files only.

1. Add `dream/bridge/methods_<domain>.py` with the `HANDLERS` contract in [the bridge extension contract](../../bridge/extension-contract.md).
2. Add `dream/<domain>/tools.py` and decorate tools with `@tool(risk=...)`.
3. Add `apps/desktop/src/routes/<domain>.tsx`. Export a default component plus `route` metadata:

```tsx
export const route = { label: 'nav.hello', path: '/hello', group: 'workspace' };
export default function HelloRoute() { return <h2>Hello</h2>; }
```

The route component remains code-split; its declarative metadata is discovered by `route-registry.ts`. `registeredNav` and `shellSlots.main` are available to future shell consumers.

4. Add `apps/desktop/src/lib/bridge/<domain>.ts` and optionally `echo-<domain>.ts`; use `createDomainBridgeClient` from `extension-client.ts` for bounded typed request/stream calls and normalized errors.
5. Add `apps/desktop/src/locales/<lang>/<domain>.json`. Locale resources and `registeredNamespaces` are glob-discovered.

Do not edit `methods.py`, `App.tsx`, `client.ts`, existing routes, or locale registries. Run the focused tests plus Python and desktop quality gates before handoff.
