# How to add a tool

Tools are schema-derived: Dream reads the function signature and docstring and
generates the JSON Schema the model sees. There is no hand-written schema to
keep in sync.

## Steps

1. **Write the function** in `dream/tools.py` with type hints and a docstring
   whose `:param …:` lines describe each argument.

   ```python
   @tool(risk="safe")
   def compute_length(text: str) -> dict[str, Any]:
       """Return the number of characters in ``text``.

       :param text: The string to measure.
       """
       return {"length": len(text)}
   ```

2. **Pick a risk tier** — `safe` (auto-run), `guarded` (auto-run, logged), or
   `dangerous` (requires approval). Prefer the *lowest* tier that is honest
   about the side effects.

3. **Register it.** The `@tool` decorator does this automatically on import; a
   tool is also auto-registered when `dream.tools` is imported by `dream/__init__.py`.

4. **Test it.** Add a test under `tests/` asserting the happy path **and** the
   refusal path (if it is `dangerous`, verify `ApprovalPolicy` denies it
   without an approver — see `tests/test_security_tool_risk.py`).

5. **Run the gates** (see `docs/dev/CONTRIBUTING.md`).

## Conventions

- Return a plain `dict` (the bridge serialises it as JSON).
- Never `print()` — log with `logging`.
- Keep arguments JSON-serialisable; use `typing` generics so the schema is
  accurate.
- `Optional[T]` arguments are unwrapped to a nullable schema automatically.
