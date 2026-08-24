# Bridge extension contract

P0 provides an add-only bridge seam. A domain may add `dream/bridge/methods_<domain>.py`; no central registration edit is needed.

## Method module

`<domain>` must match `[a-z][a-z0-9_]*`. The module exports a module-level `HANDLERS` mapping. Every key must be a dotted RPC method in that module's namespace and every value must be callable:

```python
# dream/bridge/methods_hello.py
async def greet(name: str = "world") -> dict[str, str]:
    return {"message": f"hello {name}"}

HANDLERS = {"hello.greet": greet}
```

Handlers receive JSON-RPC named parameters as keyword arguments. They may be synchronous, async, or return the bridge's supported async stream shape. Raise `BridgeError`/`DomainError`-style typed errors for expected failures; unhandled exceptions retain normal bridge internal-error mapping.

Discovery is sorted, starts once, and publishes an immutable mapping. Only files beneath installed `dream.bridge` are considered. Bad names, invalid mappings, duplicate extension methods, files outside the package, and import failures are quarantined and logged under `dream.bridge.extensions`; built-in handlers continue serving. A built-in-name collision is quarantined and refused (the built-in wins). There is no `OVERRIDE` bypass in P0.

## Tool module

Add `dream/<domain>/tools.py`, using the normal decorator:

```python
from dream.tools import tool

@tool(risk="safe")
def hello_tool(name: str) -> str:
    """Return a greeting."""
    return f"hello {name}"
```

Importing the bridge seam imports valid immediate domain tool modules once. A domain with no `tools.py` is skipped silently; failures inside a real tool module are quarantined under `dream.extensions`. No path from an RPC request, environment value, or current working directory is executed.

## Desktop route module

Add `apps/desktop/src/routes/<domain>.tsx`, where `<domain>` matches `[a-z][a-z0-9_]*`. It must default-export the page component. The registry lazy-loads that component and derives `/<domain>`, `nav.<domain>`, and the `workspace` group automatically. Optionally add `apps/desktop/src/routes/<domain>.route.ts` exporting `route = { path, label, group, icon?, slot? }` for metadata only. The activity rail consumes `registeredNav` automatically; feature work must not edit the rail, `App.tsx`, or `methods.py`.
