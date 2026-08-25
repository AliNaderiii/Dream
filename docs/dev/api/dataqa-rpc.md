# Data Q&A RPC

P3 is an add-only Dream Bridge extension. All methods use JSON-RPC object params and the `dataqa.*` namespace. Dataset values are always treated as untrusted data, never model instructions.

## Methods

| Method | Params | Result |
|---|---|---|
| `dataqa.sessions.create` | `source?`, `query?`, `dataset_id?` | session with selected dataset and schema profile |
| `dataqa.sessions.list` | none | `{sessions: [...]}` |
| `dataqa.sessions.get` | `session_id` | session and at most 20 recent turns |
| `dataqa.sessions.delete` | `session_id` | deletion status |
| `dataqa.discover` | `query?`, `source?`, `limit?` | ranked candidates, reasons, and bounded profiles |
| `dataqa.ask` | `session_id`, `question`, `timeout?`, `chart?` | streamed answer text and final result |
| `dataqa.chart` | `session_id` | latest validated chart |
| `dataqa.reset` | `session_id` | cleared working state |

`source` is workspace-relative or an absolute path inside `DREAM_WORKSPACE_ROOT`. Values outside the workspace, symlinks, unsupported oversized inputs, malformed IDs, and over-quota requests are rejected.

## Ask stream

`dataqa.ask` returns the standard Bridge `Stream`. `stream.chunk` payloads contain `{id, token}`. Cancellation closes the client request; the trusted worker also has an independent deadline and OS resource limits. The final JSON-RPC result is:

```json
{
  "session_id": "32-hex-characters",
  "final_answer": {
    "status": "ok",
    "answer": "The evidence contains 4 result rows.",
    "summary": "The evidence contains 4 result rows.",
    "language": "en",
    "grounded": true,
    "evidence": {
      "dataset": "sales",
      "columns": ["region", "mean_revenue"],
      "rows": [{"region": "North", "mean_revenue": 125.5}],
      "rows_considered": 1000,
      "operation": "aggregate"
    },
    "plan": {"action": "aggregate", "aggregate": "mean", "metric": "revenue", "groups": ["region"]},
    "generated_code": "result = df.groupby(['region'])['revenue'].mean().reset_index()",
    "chart": {"type": "bar", "format": "svg", "validated": true},
    "warnings": [],
    "sandbox": {"kind": "guarded-local", "network_enabled": false}
  }
}
```

`status` is `ok`, `insufficient_data`, `error`, or `cancelled`. Missing, ambiguous, empty, or unsupported evidence must return `insufficient_data` with “I can't determine that from this data” (or its Persian equivalent), no invented number, and empty evidence rows.

## Error mapping

- malformed params: `-32602` (`INVALID_PARAMS`)
- unavailable dataset, unsafe path, invalid session: `-32006` (`TOOL_ERROR`)
- session/output quota: `-32007` (`RESOURCE_EXHAUSTED`)
- deadline inside a valid ask is represented by `final_answer.status = cancelled`

Messages pass through Dream's secret-shape redactor. Public candidate/session DTOs never include absolute host paths. A supplied `dataset_id` is authoritative: session creation fails rather than silently selecting another ranked candidate.

## Chart contract and quotas

Validated SVG output supports category bars, time trends, histograms, box plots, two-measure scatter plots, and correlation heatmaps. Coordinates are scaled across the actual numeric domain, including negative values. Labels and points are generated only from the same bounded evidence rows returned in `final_answer`.

An SVG is at most 512 KiB. The chart directory is limited to 32 SVG assets and 4 MiB in aggregate; symbolic links are rejected. Reset and session deletion reclaim matching assets. Persisted turns omit the inline SVG and `dataqa.chart` securely reloads the bounded asset when needed.

## Execution boundary

The planner emits a closed operation plan and human-auditable pandas-equivalent Python. Generated Python is **not** evaluated. A trusted stdlib worker reads CSV, TSV, JSON/JSONL, safe flat YAML, or read-only SQLite, blocks sockets, applies resource limits, and emits bounded JSON. Excel/Parquet are discoverable and report the optional-reader limitation. When Docker is absent, every successful local result carries a loud warning that the guarded subprocess is not a container boundary.
