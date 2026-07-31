# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `run.bat` and `check.bat` launchers for Windows: `run.bat` activates
  `.venv`, clears `OPENAI_BASE_URL`/`OPENAI_API_KEY`, prompts for the Ollama
  model (`qwen2.5:7b` by default, `qwen2.5:3b` optional), and starts
  `cli.py --backend ollama`; `check.bat` runs `doctor.py --backend ollama`.
  Both pause before closing and use CRLF, pure-ASCII batch syntax.

### Fixed

- The system prompt now carries an explicit Persian memory policy: call
  `remember_fact` for durable user facts (name, work, projects, preferences,
  constraints, decisions), skip conversational filler, store one
  self-contained fact per call with a deliberate `kind` and a centrality-based
  `importance`, and store silently. A compact worked example shows the
  resulting `remember_fact` calls, so small local models follow the pattern
  instead of ignoring the tool.
- The language rule is now unconditional: always reply in the language of the
  user's most recent message, reply in Persian to Persian input, and never
  switch to a third language.
- The CLI treats a leading backslash as a command prefix, so `\mems`, `\exit`,
  and friends work exactly like their slash forms. Unknown commands suggest
  the closest known command instead of falling through to the model.
- Assistant tool calls are now recorded in chat-completions wire format
  (`type: "function"`, `name`/`arguments` nested under `function`, arguments as
  a JSON string). Conversations previously failed with HTTP 400 on the second
  turn, when the malformed history was replayed to the model.
- Optional annotations are unwrapped when deriving JSON Schema, so
  `list | None` is described as an array rather than a string. `remember_fact`
  now tells the model that `tags` is a list, matching what the code expects.
- Failed model requests report the server's response body, whitespace-collapsed
  and truncated, instead of only `HTTP Error 400: Bad Request`. API keys and
  bearer tokens are redacted from those messages.

## [0.1.0] - 2026-07-31

### Added

- Persian-aware SQLite/FTS5 memory with normalisation, suffix stemming, hybrid
  retrieval, and journal storage.
- Schema-derived tool registry with safe, guarded, and dangerous risk tiers.
- Provider-neutral agent loop with OpenAI-compatible, Ollama, and offline Echo
  backends, memory injection, and approval enforcement.
- Interactive CLI with slash commands, offline demo, and opt-in YOLO mode.
- Offline diagnostics for installation, FTS5, memory, normalisation, registry,
  approval, and optional live model tool-calling verification.
