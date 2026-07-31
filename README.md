# Dream

**Dream is a local-first personal assistant for people who write Persian as well
as English.** Its memory search treats Persian spelling variants as the same
word before storing or querying them, so a fact saved from one keyboard is still
found from another. The core package uses only Python's standard library; run
its complete demo without an API key.

## Persian retrieval that does not silently miss

These look the same in many fonts, but are different Unicode bytes:

```text
مي‌خواهم كتاب  # Arabic yeh (U+064A) and kaf (U+0643)
می‌خواهم کتاب  # Farsi yeh (U+06CC) and keheh (U+06A9)
```

Without normalisation, storing the second spelling and searching the first can
return nothing because a database compares different code points. Dream applies
NFKC, folds Arabic letter forms and digits, removes diacritics and tatweel, and
normalises whitespace on both write and read. Both examples become
`می خواهم کتاب`, so retrieval reaches the same memory. Run the demo below to
see the value printed by the program.

## Install and run

Python 3.10 or later is required.

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
dream --demo                         # no API key or network required
python doctor.py                     # verify the local installation
```

For an interactive offline session, use `dream --backend echo`. Configure a
provider only when needed; see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Windows

Double-click `run.bat` to start Dream against a local Ollama server: it
activates `.venv`, clears any OpenAI credentials, lets you pick between
`qwen2.5:7b` (default) and `qwen2.5:3b`, and launches the interactive CLI.
`check.bat` runs the offline diagnostics with `doctor.py --backend ollama`.
Both scripts pause on exit so error messages stay readable.

## Demo transcript

The following is a transcript captured by running `python cli.py --demo` in
this repository. Scores and the clock naturally vary between runs.

```text
1. Seeding memories across semantic, episodic, and procedural kinds
2. Hybrid retrieval for 'coffee':
   relevance=0.894  Visited Tehran coffee shop today
   relevance=0.888  I prefer dark coffee
3. Normalisation:
   Arabic forms  → می خواهم کتاب
   Persian forms → می خواهم کتاب
   This matters because equivalent spellings retrieve the same stored memory.
4. Agent tool loop:
   What time is it? Result: {"result": "2026-07-31T10:49:02.095406+03:30"}
   What is 12 × 3? Result: {"result": 36}
5. Approval gate:
   {"blocked": true, "reason": "dangerous tool denied: no approver configured"}
```

## Architecture at a glance

Dream stores three kinds of memory:

| Kind | Purpose |
| --- | --- |
| `semantic` | durable facts and preferences |
| `episodic` | timestamped events |
| `procedural` | instructions and learned rules |

Retrieval combines lexical relevance with time and user intent rather than
using similarity alone:

```text
score = 0.55 * relevance + 0.20 * recency + 0.15 * importance + 0.10 * usage
```

Tools are registered from Python signatures and docstrings, then assigned a
risk tier: `safe` tools run automatically; `guarded` local reversible writes
run and are logged; `dangerous` external or irreversible actions require an
approval callback. The agent loop consults that policy before every requested
tool execution.

Model backends share one `chat(messages, tools)` interface. `EchoBackend` is
the deterministic offline backend; `OpenAIBackend` speaks the OpenAI-compatible
HTTP API; `OllamaBackend` points that protocol at a local Ollama instance.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full data flow.

## Add a tool

The decorator derives the provider schema from the signature and `:param` lines;
do not maintain a second hand-written schema.

```python
from dream import tool


@tool(risk="safe")
def word_count(text: str, include_spaces: bool = False) -> int:
    """Count characters in text.

    :param text: Text to count.
    :param include_spaces: Whether whitespace counts.
    """
    return len(text) if include_spaces else len(text.replace(" ", ""))
```

Its generated JSON Schema has a required string `text`, an optional boolean
`include_spaces`, and the two descriptions above. The `safe` tier means the
agent may execute it automatically; choose `guarded` or `dangerous` when the
effect warrants it.

## Development

```bash
python -m pytest
python -m ruff check .
python -m build
```

The core `dream/` package has **no runtime dependencies**. Development tools
are available through the `dev` extra. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [CHANGELOG.md](CHANGELOG.md) for project process and release history.

## License

[MIT](LICENSE)
