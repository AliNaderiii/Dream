# P9 gates — real stdout

Recorded 2026-08-26 on the implementation tree.

## CLI

```
$ python3 -m dream.remotegw --help
usage: dream-serve [-h] [--lan] [--host HOST] [--port PORT] [--preview]
```

## Python

```
$ python3 -m pytest tests/test_remotegw.py tests/test_remotegw_security.py -q
..........                                                               [100%]
10 passed in 0.73s

$ python3 -m ruff check dream/remotegw dream/bridge/methods_remotegw.py \
    tests/test_remotegw.py tests/test_remotegw_security.py dream_serve.py
All checks passed!
```

## Locales

```
$ python3 tools/check_locales.py
Locale integrity: PASS — 8 locales × 23 namespaces; 1076 leaves
fa gate=PASS
```

## Honest residuals

- Desktop vitest was not re-run here after node_modules went missing.
  Owner CI is the frontend regression gate. Prettier was applied to the
  new TS/TSX files.
- The live scheduler / hosted model are unchanged.
- `gateway_server.py` is imported, not rewritten. Query-string tokens are
  still accepted *there*; this façade refuses them.
