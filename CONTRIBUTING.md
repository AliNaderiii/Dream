# Contributing

Thanks for improving Dream. The project keeps its runtime dependency-free and
expects changes to remain testable without credentials, a network connection,
or a GPU.

## Setup

```bash
git clone https://github.com/AliNaderiii/Dream.git
cd Dream
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

Use `python cli.py --demo` for an offline end-to-end check and `python
doctor.py` for local prerequisites.

## Making a change

- Keep `dream/` limited to the Python standard library.
- Add or update focused tests in `tests/test_dream.py` for every behaviour
  change, particularly approval and filesystem boundaries.
- Run `python -m pytest` and `python -m ruff check .` before opening a pull
  request.
- Keep tool schemas derived from the decorated function's signature and
  docstring. Do not add a hand-written duplicate schema.
- Treat dangerous external effects as denied until a tested approval path
  permits them.

## Pull requests

A good pull request has one clear purpose, a descriptive title, tests that show
the new behaviour and its safety boundary, and a short summary of verification
commands. Explain any user-visible migration or configuration change. Avoid
mixing formatting-only changes with runtime behaviour unless formatting is the
purpose of the pull request.
