# Ask questions about your data

Open **Data Q&A** from Dream's workspace navigation. The page works in left-to-right and right-to-left layouts and accepts English or Persian questions.

## 1. Find a dataset

Enter an optional workspace file or folder and describe the data you want. Leaving Source blank searches Dream's registry and supported files in the workspace. Results are ranked from file names, paths, schema, metadata, Persian-aware normalization, and lexical concept matches. Each result explains why it matched.

Supported without extra packages: CSV, TSV, JSON, JSONL, simple flat YAML, and SQLite. Excel and Parquet can be discovered, but Dream tells you when an optional reader is unavailable.

## 2. Inspect and ask

Choose a result. Dream shows a compact schema card with data types, null counts, unique values, ranges, and category summaries. Ask questions such as:

- `What is the average revenue by region?`
- `Show sales for North only.`
- `میانگین درآمد به تفکیک منطقه چقدر است؟`
- `توزیع مبلغ فروش را رسم کن.`
- `Show the revenue trend over date.`
- `Plot the relationship between revenue and cost.`
- `Show a correlation matrix for the numeric columns.`

A result contains the answer, exact evidence rows, rows considered, generated pandas-equivalent code, and a validated chart when one is justified. Charts are rendered only from the evidence returned with the answer.

## Follow-ups and reset

Follow-ups compose with the latest grounded plan. For example, after asking for average revenue by region, ask `What about North?`. Select **Reset** to remove filters and working analysis state while keeping the dataset.

## Honest uncertainty

Dream says **“I can't determine that from this data”** / **«از این داده‌ها قابل تعیین نیست.»** when a measure or grouping is missing, ambiguous, unsupported, or has no usable values. It does not fill gaps with general knowledge or retain ungrounded numbers.

## Safety and limits

- Dataset paths must remain inside the Dream workspace.
- Dataset cells are data, never instructions. Suspicious instruction-like rows are rejected and reported.
- Secret-shaped values are removed from output and errors.
- Worker networking is disabled; operations have deadlines, memory/CPU/file limits, and bounded output.
- If Docker is unavailable, Dream uses a guarded local process and shows a warning because this is weaker than a container boundary.
- Interactive queries are limited to 250,000 rows, 256 columns, and 200 evidence rows.
- Each generated SVG is capped at 512 KiB; the chart directory is capped at 32 assets and 4 MiB total. Resetting or deleting a session removes its chart assets.
- Session history retains the latest 20 turns and has a 24 MiB serialized-state ceiling.

If an operation exceeds its deadline it terminates with a cancellation result rather than leaving a spinner running.
