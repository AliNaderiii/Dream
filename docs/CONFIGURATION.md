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

`doctor.py --backend …` tests actual tool calling, not just a successful text
response. If it reports no tool call, select a model that supports tool/function
calling or check the endpoint and model configuration.

## Safety

Dangerous tools are denied by default when no approval callback is configured.
The interactive CLI's `--yolo` switch deliberately widens automatic approval to
include them and prints a warning. It is not enabled by any environment
variable and is not the default.
