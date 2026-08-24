# Add a domain the parallel way

P0 lets a feature ship as new files only.

1. Add `dream/bridge/methods_<domain>.py` with the `HANDLERS` contract in [the bridge extension contract](../../bridge/extension-contract.md). Built-in RPC names are quarantined and refused; there is no `OVERRIDE` escape hatch.
2. Optionally add `dream/<domain>/tools.py` and decorate tools with `@tool(risk=...)`. A missing `tools.py` is normal and silent.
3. Add `apps/desktop/src/routes/<domain>.tsx` (where `<domain>` matches `[a-z][a-z0-9_]*`) with a **default export** page component. It is lazy-loaded and defaults to path `/<domain>`, label `nav.<domain>`, and group `workspace`.
4. For custom route metadata only, add the tiny sibling `apps/desktop/src/routes/<domain>.route.ts`:

```ts
export const route = { path: '/hello', label: 'nav.hello', group: 'workspace' };
```

The activity rail automatically consumes `registeredNav`; do not edit the rail, `App.tsx`, or `methods.py`.

5. Add `apps/desktop/src/lib/bridge/<domain>.ts` and optionally `echo-<domain>.ts`; use `createDomainBridgeClient` from `extension-client.ts` for bounded typed request/stream calls and normalized errors.
6. Add `apps/desktop/src/locales/<lang>/<domain>.json`. Locale resources and `registeredNamespaces` are glob-discovered.

Run focused tests plus the Python and desktop quality gates before handoff.
