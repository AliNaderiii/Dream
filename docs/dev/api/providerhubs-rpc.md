# Provider hubs RPC

P5 adds an optional `providerhubs.*` family for the local-runtime matrix, the curated catalog, tool-call diagnostics, and the optional tool gateway. The desktop wrapper routes `transportKind === 'echo'` to a deterministic local runtime so the providers page works without a sidecar. Live adapters may be absent in CI; echo and mock probes are the hermetic path.

Credentials never appear in params, results, `--route` sentences, or traces. Probes are one bounded request and send no secrets.

## Methods

| Method | Params | Result |
|---|---|---|
| `providerhubs.catalog` | `query?` | curated catalog entries (local vs cloud, cost tier, privacy EN+FA) |
| `providerhubs.runtimes` | none | Ollama, vLLM, SGLang, llama.cpp, LM Studio, generic |
| `providerhubs.health` | `runtime_id` | cheap health bit (`healthy` / `down` / `unknown` / `idle`) |
| `providerhubs.models` | `runtime_id` | model ids and the selected model |
| `providerhubs.select_model` | `runtime_id`, `model` | updated runtime record |
| `providerhubs.test` | `runtime_id` | doctor-style probe (`ok`, `latency_ms`, `secrets_sent: false`) |
| `providerhubs.diagnose` | `runtime_id` | why tool calls are not firing, plus a fix string (EN+FA) |
| `providerhubs.route` | none | fixed priority `hosted → aval → ollama → byok → echo` |
| `providerhubs.gateway` | none | optional tool gateway (web search, image, speech, browser) |
| `providerhubs.gateway_update` | `enabled?`, `tool_id?`, `tool_enabled?`, `byok?` | updated gateway |
| `providerhubs.parsers` | none | parser registry (`function_tools`, qwen, llama3, mistral, hermes, deepseek, glm, `generic_fallback`) |

`runtime_id` is one of `ollama`, `vllm`, `sglang`, `llamacpp`, `lmstudio`, `generic`. Unknown ids are rejected before a wire call.

## Honesty rules

- Cost tiers are `local`, `byok`, or `optional`. No invented currency amounts.
- Local is the recommended default. A cloud key is never required to chat.
- The generic fallback parser sets `reduced_reliability: true` in diagnostics and the UI.
- Route priority is fixed: hosted → aval → ollama → byok → echo.

## Diagnostic fixes

| Runtime | Actionable hint |
|---|---|
| Ollama | Tool calling is on by default. |
| vLLM | `--enable-auto-tool-choice --tool-call-parser qwen` (or the matching family). |
| SGLang | `--tool-call-parser mistral` (or the matching family). |
| llama.cpp | `llama-server --jinja`. |
| LM Studio | Enable structured output / tools in the local server settings. |
| Generic | Fallback text parser; expect reduced reliability. |

## Gateway

The tool gateway is optional and per-tool. Local chat works when it is off. Tokens are scoped, stored in the OS keychain, and never rendered by this UI.
