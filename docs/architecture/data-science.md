# Data Science Pipeline (P-09)

Dream's data-science pipeline lets the agent take a request like *"load
`~/datasets/sales-2024.csv`, clean it, run a correlation matrix, chart revenue
by region, and write a PDF report"* end to end — with every heavy computation
inside the P-08 Docker sandbox and the host handling only validation, small
structured results, and file bookkeeping.

## 1. Architecture

```
 chat / tools                bridge RPC                 sandbox
┌───────────────┐   data.*  ┌─────────────────────┐    ┌──────────────────────┐
│ agent loop    │──────────▶│ BridgeMethods       │    │ docker container     │
│ (load_data,   │           │  └ DataScienceRuntime│──▶│  pandas / numpy /    │
│  clean_data,  │  notebook.*│     ├ DatasetManager │   │  scipy / sklearn /   │
│  create_chart │──────────▶│     └ executor ──────┼──▶│  matplotlib/seaborn  │
│  ...)         │           │ NotebookManager      │    │  (network disabled)  │
└───────────────┘           └─────────────────────┘    └──────────────────────┘
        │                        │      ▲                        │
        ▼                        ▼      │ _result.json           ▼
 desktop workbench      data/datasets/{id}/…            charts/, report.pdf,
 (/data routes)         index.json registry             cleaned.csv, *.ipynb
```

Three host-side pieces:

- **`dream/skills/data_science.py`** — the tool suite. Owns the dataset
  registry (`DatasetManager`), request validation, script generation, and the
  executor seam (`SandboxCodeExecutor` → Docker, `LocalPythonExecutor` →
  dev/test fallback via `DREAM_DATA_LOCAL_EXEC=1`).
- **`dream/skills/notebooks.py`** — Jupyter integration. nbformat-v4 file IO
  is plain JSON on the host; execution goes through `jupyter_client` with one
  kernel per `dataset_id`; `open_jupyterlab` spawns a token-guarded local
  JupyterLab rooted at the datasets directory.
- **`dream/bridge/methods.py`** — the `data.*` / `notebook.*` RPC families
  (see `docs/bridge/protocol.md` §3.12–3.13). Runtime calls run in
  `asyncio.to_thread`, and every `DataScienceError` maps to
  `INVALID_PARAMS (-32602)`.

## 2. Execution model

The host never imports pandas/matplotlib/scipy (the `dream/` runtime adds
zero third-party dependencies). Each operation compiles to a short generated
script that:

1. reads its parameters from `_params.json` — parameters are **never**
   interpolated into code, closing the injection channel;
2. loads the dataset's active file (`source.{ext}` or `cleaned.csv`);
3. does one job (profile / clean / analyze / chart / report);
4. writes `_result.json`, which the host parses and returns over RPC.

The default executor mounts `data/datasets/{id}/` read-write into a container
with the full P-08 hardening (no network, cap-drop ALL, seccomp,
no-new-privileges, memory/pids limits). Outputs land inside that directory
only.

## 3. Dataset registry

Datasets are referenced by a 32-hex `dataset_id`, never by raw path — the
agent cannot escape the workspace after ingestion. On `load_data` the source
file is *copied* into `data/datasets/{id}/source.{ext}` and registered in
`data/datasets/index.json` with shape, columns, dtypes, and column metadata.
`clean_data` writes `cleaned.csv` and flips the record's active file; every
later operation reads the cleaned data. `delete_dataset` removes the
directory, the registry row, and shuts down any notebook kernel bound to the
dataset.

Supported formats (auto-detected by extension, content-sniffed for ambiguous
ones): CSV, TSV, Excel (`.xlsx`/`.xls`), JSON, YAML, XML, SQLite, Parquet.
Files over 100 MB profile via chunked aggregation; ingestion caps at 500 MB.

## 4. Validation & error model

All request validation happens host-side against closed allowlists:

| Surface | Allowlist |
| --- | --- |
| Cleaning ops | `drop_na fill_na convert_dtype remove_duplicates rename_column drop_column filter_rows normalize_column encode_categorical handle_outliers` |
| Analyses | `correlation ttest anova chi_square linear_regression logistic_regression kmeans pca time_series_decompose` |
| Chart types | `line bar scatter histogram box heatmap pie area bubble` |
| Themes | `default minimal dark ggplot seaborn` (missing styles fall back, never crash) |
| Palettes | `viridis plasma inferno Set1 Set2 Pastel1 custom` (custom = validated `#RRGGBB` list) |
| Sizes | width 200–4096, height 150–4096, dpi ∈ {72, 96, 150, 300} |

Column references must match `^[A-Za-z_][A-Za-z0-9_]*$` (≤ 64 chars) **and**
exist in the recorded schema; `clean_data` tracks renames/drops so a pipeline
validates against the schema each op produces. Filter values must be scalars
(or bounded lists for `in`/`not_in`).

Failure tiers:

- **Validation failure** — raised host-side as `DataScienceError` before any
  sandbox run; surfaces as `INVALID_PARAMS` with the exact reason.
- **Per-analysis failure** — `analyze_data` marks that entry
  `{"status": "error", ...}` and continues the batch.
- **Sandbox failure** — non-zero exit or missing `_result.json` raises with
  the stderr tail; timeouts raise a distinct timeout message.
- **Notebook unavailability** — missing `jupyter_client`/JupyterLab maps to
  bridge code `-32012` so the UI can degrade gracefully.

Charts are quota-checked (5 MB per export); over-quota renders are deleted
and rejected. Reports cap at 5 pages, embed at most 6 charts, and DOI
references are static text — report generation never touches the network.

## 5. Frontend workbench

`/data` lists the registry; `/data/:datasetId` is the workbench with five
tabs: **Preview** (TanStack Table — sort/filter/paginate/column-resize/cell
copy), **Profile** (headline stats + expandable per-column cards with mini
histograms), **Charts** (ranked auto-chart suggestions, gallery with
downloads), **Notebook** (inline cell render, per-cell run, Open in
JupyterLab), and **Report** (markdown preview + PDF download). Typed
wrappers live in `apps/desktop/src/lib/bridge/data-science.ts`; the echo
transport (`echo-data.ts`) seeds a deterministic 1,000-row `sales-2024`
dataset, a chart, a notebook with outputs, and a report so browser dev works
with no sidecar.

## 6. Iranian office files (S02)

`load_data` has to survive the files Iranian companies actually send. The
host never imports pandas; encoding sniff and header matching stay in
stdlib, and digit folding runs inside the generated sandbox script.

### Encodings (CSV / TSV)

`sniff_text_encoding` reads a 64 KiB sample (never the whole file) and
returns one of:

| Encoding | How it is recognised |
| --- | --- |
| `utf-8-sig` | leading `EF BB BF` BOM |
| `utf-8` | sample decodes strictly as UTF-8 (covers ASCII) |
| `cp1256` | otherwise treated as Windows Arabic/Persian |

The sniffed name is stored on the dataset record and passed to the sandbox
via `_params.json` so `pd.read_csv(..., encoding=…)` and the chunked
profiler use the same codec. After `clean_data` the active file is
`cleaned.csv` (UTF-8) and the record's encoding is reset to `utf-8`. The
500 MB ingest cap and the 100 MB chunked-profile threshold are unchanged.

Committed fixtures: `examples/iranian-sales-cp1256.csv` (real cp1256
bytes, not valid UTF-8) and `examples/iranian-sales-utf8-sig.csv` (BOM +
Persian digits).

### Persian digits

Before any numeric coerce, the sandbox translates Persian (`U+06F0–U+06F9`)
and Arabic-Indic (`U+0660–U+0669`) digits to Latin, maps the Arabic decimal
separator (`U+066B`) to `.`, and drops the Arabic thousands separator
(`U+066C`). A column becomes numeric only when every non-blank cell
converts; mixed text stays text (with digits folded).

### Headers: yeh / kaf matching, display not rewritten

Displayed column names are the file's own spelling after decode. Arabic yeh
(`ي` U+064A) / kaf (`ك` U+0643) vs Farsi yeh (`ی` U+06CC) / keheh (`ک`
U+06A9) are folded only when matching a request against the schema, using
the existing `normalize_fa`. Exact match wins; a folded hit returns the
**displayed** name so later sandbox ops see the real header. Office-style
headers (Persian letters, spaces, light punctuation) are accepted by the
column checker; injection characters (`;`, `/`, quotes, …) are still
refused.
