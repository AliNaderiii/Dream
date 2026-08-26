# P10 gates — real stdout

Recorded 2026-08-26 on the implementation tree before owner land.

## Python unit tests (new)

```
$ python3 -m pytest tests/test_space.py tests/test_space_security.py -q
...............                                                          [100%]
15 passed in 0.26s
```

## Ruff (owned files)

```
$ python3 -m ruff check dream/space dream/bridge/methods_space.py tests/test_space.py tests/test_space_security.py
All checks passed!
```

## Locales

```
$ python3 tools/check_locales.py
Locale integrity: PASS — 8 locales × 22 namespaces; 1060 leaves and identical key/type/placeholder trees.
English fallback counts: fa=0, zh-CN=372, ja=372, es=372, de=372, fr=372, ko=372; fa gate=PASS
```

## Desktop (owned + registry)

```
$ npx tsc --noEmit
(exit 0)

$ npx eslint src/routes/space.tsx src/routes/space.route.ts src/routes/space.test.tsx src/lib/bridge/space.ts src/lib/bridge/echo-space.ts src/lib/bridge/space.test.ts
(exit 0)

$ npx vitest run src/routes/space.test.tsx src/lib/bridge/space.test.ts src/lib/route-registry.test.ts
 Test Files  3 passed (3)
      Tests  6 passed (6)
```

## Honest residuals

- Full `pytest` in this sandbox timed out on pre-existing suites (not Space).
  Owner CI on the PR is the regression gate.
- `tests/security/test_sec_surfaces_f.py::test_audit_script_fails_when_a_layer_breaks`
  failed here with `No module named 'dream'` in a subprocess — pre-existing
  environment issue, not a Space change.
- Approved drafts are stored; they are not registered on the live scheduler.
- `space.ask` is a local briefing, not a hosted model turn.
