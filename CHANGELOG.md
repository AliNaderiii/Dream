# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

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
