# Quick Start — Dream in five minutes

This file is the only thing you need to get from "installed" to "first
conversation". It assumes Python 3.10 or later and an internet connection only
for the optional model-provider step.

## 1. Install

```bash
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## 2. Run the offline demo (no key, no network)

```bash
dream --demo
```

This runs a complete conversation against the built-in **echo** backend — no
API key and no network required — so you can confirm the install works and see
the memory + approval flow end to end.

## 3. Configure a real model (optional)

```bash
python doctor.py                  # verify the installation
```

To use a model, pick one backend:

- **Ollama (local, free):** `dream --backend ollama`
- **OpenAI-compatible:** set `OPENAI_API_KEY` (and optionally
  `OPENAI_BASE_URL`) in your environment, then run `dream`.

API keys go to your operating-system keychain (Keychain Access / Windows
Credential Manager / Linux Secret Service) — they are never written to a
settings file.

## 4. First conversation

```text
> سلام! اسم من مریم است.    (or: "Hi! My name is Mary.")
```

Dream replies in the language you used. Say `/mems` to see what it has stored,
or `/help` for the command list.

## 5. Try the desktop app

The Tauri desktop shell (the full UI) is built from `apps/desktop`:

```bash
cd apps/desktop && npm install && npm run dev
```

That's it — you're up and running in under five minutes.
