# How to add a provider

A provider is a model backend the agent can talk to. The catalogue entry is
user-facing; the backend is the transport.

## Steps

1. **Add a catalogue entry** in `apps/desktop/src/types/index.ts`
   (`ProviderCatalogEntry`) with the provider's kind, endpoint, auth type, and
   default models. The provider list in `dream/` must expose the same kind.

2. **Implement the backend** in `dream/` (e.g. alongside `OpenAIBackend` and
   `OllamaBackend` in `dream/agent.py`): a callable that takes the prompt
   history and returns the model's completion text. Echo backends (offline) are
   welcome for dev parity.

3. **Wire it into `build_backend`** so `--backend <name>` resolves it.

4. **Frontend form** (if it has configurable fields): add it to the provider
   editor in `apps/desktop/src/routes/providers.tsx`, and add its i18n keys to
   `apps/desktop/scripts/generate-locales.mjs` (all eight languages).

5. **Credential handling:** API keys go through `keyring`, never into settings
   files or logs.

6. **Test it** with a live or echo transport and run the gate suite.

## Conventions

- `ProviderKind` in `apps/desktop/src/types/index.ts` is the single source of
  truth for the kind string.
- Local providers (Ollama, vLLM, llama.cpp) set `local: true` so the UI shows
  the right badge and skips egress warnings.
