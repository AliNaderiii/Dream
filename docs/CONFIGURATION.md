# Configuration

Dream works offline with the default `echo` backend. Environment variables are
optional and are read when a backend or workspace is constructed.

| Variable | Controls | Default | Applies to |
| --- | --- | --- | --- |
| `DREAM_BACKEND` | Backend selected by `build_backend()` | `echo` | all entry points using the default backend |
| `DREAM_MODEL` | Model identifier | empty for OpenAI-compatible; `llama3.2` for Ollama | OpenAI, Ollama |
| `OPENAI_API_KEY` | Bearer token sent to an OpenAI-compatible endpoint | empty | OpenAI-compatible |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` | OpenAI-compatible |
| `OLLAMA_HOST` | Local Ollama host, before the `/v1` compatibility path | `http://localhost:11434` | Ollama |
| `DREAM_WORKSPACE_ROOT` | Root directory available to note/file tools | current working directory | tools |
| `DREAM_SYNONYMS` | Path to a JSON file of extra Persian synonym groups for query expansion; malformed files fall back to the built-in table | built-in table only | memory |
| `DREAM_MAX_RETRIES` | Retry attempts for HTTP 429 rate limits, with exponential backoff | `3` | OpenAI, Ollama |
| `DREAM_RETRY_BACKOFF_SECONDS` | Base backoff sleep before the first retry; each retry doubles it | `1.0` | OpenAI, Ollama |
| `DREAM_EXTRACTION_TIMEOUT_SECONDS` | Wall-clock budget a turn waits for the background extraction pass before marking it abandoned | `5.0` | all backends |

The CLI can override backend selection with `--backend echo`, `--backend
openai`, or `--backend ollama`. Its `--db` flag controls the SQLite memory path
and defaults to `data/dream.db`. `--owner` only changes the CLI greeting.

## Examples

Offline, no credentials:

```bash
dream --backend echo
```

An OpenAI-compatible provider:

```bash
export DREAM_BACKEND=openai
export DREAM_MODEL=your-tool-capable-model
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://provider.example/v1
dream
python doctor.py --backend openai
```

Local Ollama:

```bash
export DREAM_MODEL=llama3.2
export OLLAMA_HOST=http://localhost:11434
dream --backend ollama
python doctor.py --backend ollama
```

On Windows the primary launcher is `run.bat`. It sets `DREAM_MODEL=qwen2.5:7b`
(unless you already set one) and starts `cli.py --backend ollama`. If Ollama
is not installed it prints a Persian + English message pointing at
<https://ollama.com/download> and pauses. The library default remains
`llama3.2` when `DREAM_MODEL` is unset. Offline diagnostics:
`python doctor.py` or double-click `check.bat`.

`doctor.py --backend …` tests actual tool calling, not just a successful text
response. If it reports no tool call, select a model that supports tool/function
calling or check the endpoint and model configuration.

## Safety

Dangerous tools are denied by default when no approval callback is configured.
The interactive CLI's `--yolo` switch deliberately widens automatic approval to
include them and prints a warning. It is not enabled by any environment
variable and is not the default.

## Durable learning and context

| Variable | Controls | Default |
| --- | --- | --- |
| `DREAM_BOUNDED_DB` | SQLite path for bounded agent notes and user profile | `data/dream-bounded.db` |
| `DREAM_SESSION_INDEX_DB` | SQLite FTS5 session-search index | `data/dream-session-index.db` |
| `DREAM_SKILLS_DB` | SQLite skill-use ledger | implementation default |
| `DREAM_SKILL_PROPOSALS` | SQLite skill-improvement proposal store | implementation default |
| `DREAM_CONTEXT_TOKENS` | Context window used by local compaction accounting | echo `16384`, model `8192` |
| `DREAM_COMPACTION_THRESHOLD` | Fraction of the window that triggers boundary compaction | `0.80` |
| `DREAM_COMPACTION_KEEP_MESSAGES` | Recent active messages protected from compaction | `4` |
| `DREAM_MEMORY_NUDGES` | Enables prompt-only durable-memory nudge (`off`, `false`, or `0` disables) | enabled |
| `DREAM_MEMORY_NUDGE_EVERY_TURNS` | Turns before the once-per-session nudge becomes eligible | `8` |

Compaction runs only at turn boundaries. `/compress` requests it explicitly.
Nudges are never issued in demo mode and never write data themselves.
