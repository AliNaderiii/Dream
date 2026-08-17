/**
 * Deterministic echo runtime for the `data.*` / `notebook.*` families.
 *
 * Browser dev and vitest have no sidecar, so the workbench renders against
 * this in-memory model. Everything is generated from a fixed linear
 * congruential seed: the same build always shows the same 1,000-row
 * sales-2024 dataset, the same profile numbers, the same chart spec, the
 * same notebook outputs, and the same report markdown.
 */

import { BridgeRpcError } from './errors';
import type {
  ChartResultDto,
  ChartSpecDto,
  CleanOpDto,
  DatasetProfileDto,
  NotebookCellDto,
  RpcParams,
} from './types';

const SEED_DATASET_ID = 'ec40da7a5eed4e058e21be0dd4ca11b0';

const REGIONS = ['north', 'south', 'east', 'west'] as const;
const PRODUCTS = ['starter', 'standard', 'premium'] as const;

/** Deterministic PRNG (LCG) — same seed, same rows, every run. */
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

interface SalesRow extends Record<string, unknown> {
  invoice_date: string;
  region: string;
  product: string;
  price: number | null;
  quantity: number;
  revenue: number;
  email: string | null;
}

/** ~1k rows with dates, categoricals, numerics, and planted missing values. */
export function seedSalesRows(count = 1000): SalesRow[] {
  const random = makeRandom(20240109);
  const rows: SalesRow[] = [];
  for (let i = 0; i < count; i += 1) {
    const month = Math.floor(random() * 12);
    const day = Math.floor(random() * 28);
    const region = REGIONS[Math.floor(random() * REGIONS.length)];
    const product = PRODUCTS[Math.floor(random() * PRODUCTS.length)];
    const missingPrice = random() < 0.03;
    const price = missingPrice ? null : Math.round((20 + random() * 180) * 100) / 100;
    const quantity = 1 + Math.floor(random() * 9);
    const missingEmail = random() < 0.05;
    rows.push({
      invoice_date: `2024-${String(month + 1).padStart(2, '0')}-${String(day + 1).padStart(2, '0')}`,
      region,
      product,
      price,
      quantity,
      revenue: price === null ? 0 : Math.round(price * quantity * 100) / 100,
      email: missingEmail ? null : `buyer${i}@example.com`,
    });
  }
  return rows;
}

const SEED_COLUMNS = ['invoice_date', 'region', 'product', 'price', 'quantity', 'revenue', 'email'];

const SEED_DTYPES: Record<string, string> = {
  invoice_date: 'object',
  region: 'object',
  product: 'object',
  price: 'float64',
  quantity: 'int64',
  revenue: 'float64',
  email: 'object',
};

const SEED_CHART_SPEC: ChartSpecDto = {
  type: 'bar',
  dataset_id: SEED_DATASET_ID,
  x: 'region',
  y: 'revenue',
  theme: 'default',
  palette: 'viridis',
  title: 'Revenue by region',
};

const SEED_NOTEBOOK_CELLS: NotebookCellDto[] = [
  {
    cell_type: 'markdown',
    source: '# Sales 2024 — exploration\n\nLoaded via the Dream data workbench.',
  },
  {
    cell_type: 'code',
    source:
      "import pandas as pd\ndf = pd.read_csv('cleaned.csv')\ndf.groupby('region')['revenue'].sum()",
    execution_count: 1,
    outputs: [
      {
        type: 'execute_result',
        text: 'region\neast     41210.55\nnorth    39864.20\nsouth    43711.90\nwest     40155.75\nName: revenue, dtype: float64',
      },
    ],
  },
];

const SEED_REPORT_MARKDOWN = [
  '# Sales 2024 Annual Review',
  '',
  '## Abstract',
  '',
  "This report summarises the dataset 'sales-2024' (1000 rows x 7 columns). It covers data quality, descriptive statistics, and the charts generated during the analysis session.",
  '',
  '## Data Summary',
  '',
  'Rows: 1000    Columns: 7',
  'Missing cells: 81 (1.16% of all cells)',
  'Duplicate rows: 0',
  'Numeric columns: 3',
  '',
  '## Results',
  '',
  'Descriptive statistics for the numeric columns appear in the table below; generated charts follow on the next page.',
  '',
  '## Conclusion',
  '',
  'The dataset is ready for downstream analysis. Re-run profiling after any further cleaning to keep the summary current.',
  '',
  '## Charts',
  '',
  '![chart](charts/echo-chart-01.png)',
  '',
].join('\n');

interface EchoDatasetState {
  dataset_id: string;
  name: string;
  filename: string;
  format: string;
  created_at: number;
  rows: SalesRow[];
  columns: string[];
  dtypes: Record<string, string>;
  cleaned: boolean;
  reportMarkdown: string | null;
  notebooks: Map<string, NotebookCellDto[]>;
  charts: ChartResultDto[];
}

function numericStats(values: number[]): {
  count: number;
  mean: number;
  std: number;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
} {
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  const mean = sorted.reduce((s, v) => s + v, 0) / n;
  const variance = n > 1 ? sorted.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1) : 0;
  const quantile = (q: number) => {
    const pos = q * (n - 1);
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  };
  return {
    count: n,
    mean,
    std: Math.sqrt(variance),
    min: sorted[0],
    q1: quantile(0.25),
    median: quantile(0.5),
    q3: quantile(0.75),
    max: sorted[n - 1],
  };
}

function requireString(params: RpcParams, key: string): string {
  const value = params[key];
  if (typeof value !== 'string' || !value.trim()) {
    throw new BridgeRpcError({ code: -32602, message: `${key} must be a non-empty string` });
  }
  return value;
}

/** The deterministic in-memory data workbench used by EchoBridgeTransport. */
export class EchoDataRuntime {
  private datasets = new Map<string, EchoDatasetState>();
  private chartCounter = 0;

  constructor() {
    const rows = seedSalesRows();
    const notebooks = new Map<string, NotebookCellDto[]>();
    notebooks.set(
      `${SEED_DATASET_ID}/notebooks/exploration.ipynb`,
      SEED_NOTEBOOK_CELLS.map((cell) => ({ ...cell })),
    );
    this.datasets.set(SEED_DATASET_ID, {
      dataset_id: SEED_DATASET_ID,
      name: 'sales-2024',
      filename: 'sales-2024.csv',
      format: 'csv',
      created_at: 1704790800,
      rows,
      columns: [...SEED_COLUMNS],
      dtypes: { ...SEED_DTYPES },
      cleaned: false,
      reportMarkdown: SEED_REPORT_MARKDOWN,
      notebooks,
      charts: [],
    });
    // One pre-rendered chart so the gallery is never empty in dev.
    this.datasets.get(SEED_DATASET_ID)!.charts.push({
      chart_id: 'echo-chart-01',
      dataset_id: SEED_DATASET_ID,
      spec: SEED_CHART_SPEC,
      files: {
        png: `${SEED_DATASET_ID}/charts/echo-chart-01.png`,
        svg: `${SEED_DATASET_ID}/charts/echo-chart-01.svg`,
        pdf: `${SEED_DATASET_ID}/charts/echo-chart-01.pdf`,
        html: `${SEED_DATASET_ID}/charts/echo-chart-01.html`,
      },
      sizes: { png: 24576, svg: 18320, pdf: 15104, html: 2048 },
    });
  }

  private dataset(params: RpcParams): EchoDatasetState {
    const id = requireString(params, 'dataset_id');
    const state = this.datasets.get(id);
    if (!state) {
      throw new BridgeRpcError({ code: -32602, message: `unknown dataset: ${id}` });
    }
    return state;
  }

  handles(method: string): boolean {
    return method.startsWith('data.') || method.startsWith('notebook.');
  }

  handle(method: string, params: RpcParams): unknown {
    switch (method) {
      case 'data.list_datasets':
        return {
          datasets: [...this.datasets.values()]
            .sort((a, b) => b.created_at - a.created_at)
            .map((d) => ({
              dataset_id: d.dataset_id,
              name: d.name,
              filename: d.filename,
              format: d.format,
              created_at: d.created_at,
              shape: [d.rows.length, d.columns.length],
              columns: d.columns,
              cleaned: d.cleaned,
            })),
        };
      case 'data.get_dataset': {
        const d = this.dataset(params);
        return {
          dataset_id: d.dataset_id,
          name: d.name,
          filename: d.filename,
          format: d.format,
          created_at: d.created_at,
          active_file: d.cleaned ? 'cleaned.csv' : 'source.csv',
          shape: [d.rows.length, d.columns.length],
          columns: d.columns,
          dtypes: d.dtypes,
          column_meta: [],
          memory_bytes: d.rows.length * 96,
          cleaned: d.cleaned,
          preview: d.rows.slice(0, 50),
        };
      }
      case 'data.load_data': {
        const filePath = requireString(params, 'file_path');
        const nameParam = typeof params['name'] === 'string' ? params['name'] : '';
        const stem = filePath.split(/[\\/]/).pop() ?? 'dataset.csv';
        const id = `echo${Date.now().toString(16)}${'0'.repeat(32)}`.slice(0, 32);
        const rows = seedSalesRows(200);
        this.datasets.set(id, {
          dataset_id: id,
          name: nameParam || stem.replace(/\.[^.]+$/, ''),
          filename: stem,
          format: 'csv',
          created_at: Math.floor(Date.now() / 1000),
          rows,
          columns: [...SEED_COLUMNS],
          dtypes: { ...SEED_DTYPES },
          cleaned: false,
          reportMarkdown: null,
          notebooks: new Map(),
          charts: [],
        });
        return {
          dataset_id: id,
          name: nameParam || stem,
          filename: stem,
          format: 'csv',
          shape: [rows.length, SEED_COLUMNS.length],
          columns: SEED_COLUMNS,
          dtypes: SEED_DTYPES,
          memory_bytes: rows.length * 96,
          preview: rows.slice(0, 50),
        };
      }
      case 'data.profile_data': {
        const d = this.dataset(params);
        const profile: DatasetProfileDto = {
          dataset_id: d.dataset_id,
          sampled: false,
          row_count: d.rows.length,
          column_count: d.columns.length,
          duplicate_rows: 0,
          missing_pct: 0,
          columns: {},
        };
        let missingTotal = 0;
        for (const column of d.columns) {
          const values = d.rows.map((row) => row[column]);
          const missing = values.filter((v) => v === null || v === undefined || v === '').length;
          missingTotal += missing;
          const numbers = values.filter((v): v is number => typeof v === 'number');
          if (numbers.length > 0 && numbers.length >= values.length - missing) {
            const stats = numericStats(numbers);
            const iqr = stats.q3 - stats.q1;
            const lo = stats.q1 - 1.5 * iqr;
            const hi = stats.q3 + 1.5 * iqr;
            profile.columns[column] = {
              dtype: d.dtypes[column] ?? 'float64',
              role: 'numeric',
              missing,
              missing_pct: (missing / d.rows.length) * 100,
              unique: new Set(numbers).size,
              ...stats,
              outliers_iqr: numbers.filter((v) => v < lo || v > hi).length,
              outliers_zscore: 0,
              histogram: buildHistogram(numbers),
            };
          } else {
            const counts = new Map<string, number>();
            for (const value of values) {
              if (value === null || value === undefined || value === '') continue;
              const key =
                typeof value === 'string'
                  ? value
                  : typeof value === 'number' || typeof value === 'boolean'
                    ? value.toString()
                    : JSON.stringify(value);
              counts.set(key, (counts.get(key) ?? 0) + 1);
            }
            const top = [...counts.entries()]
              .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
              .slice(0, 10)
              .map(([value, count]) => ({ value, count }));
            profile.columns[column] = {
              dtype: d.dtypes[column] ?? 'object',
              role:
                column === 'invoice_date' ? 'datetime' : counts.size <= 50 ? 'categorical' : 'text',
              missing,
              missing_pct: (missing / d.rows.length) * 100,
              unique: counts.size,
              top_values: top,
            };
          }
        }
        profile.missing_pct = (missingTotal / (d.rows.length * d.columns.length)) * 100;
        return profile;
      }
      case 'data.clean_data': {
        const d = this.dataset(params);
        const operations = params['operations'];
        if (!Array.isArray(operations) || operations.length === 0) {
          throw new BridgeRpcError({
            code: -32602,
            message: 'operations must be a non-empty list',
          });
        }
        const before = d.rows.length;
        let rows = [...d.rows];
        const applied: string[] = [];
        for (const raw of operations as CleanOpDto[]) {
          if (raw.op === 'drop_na') {
            const subset = raw.columns ?? d.columns;
            rows = rows.filter((row) =>
              subset.every((c) => row[c] !== null && row[c] !== undefined && row[c] !== ''),
            );
          } else if (raw.op === 'drop_column' && raw.column) {
            d.columns = d.columns.filter((c) => c !== raw.column);
          } else if (raw.op === 'remove_duplicates') {
            const seen = new Set<string>();
            rows = rows.filter((row) => {
              const key = JSON.stringify(row);
              if (seen.has(key)) return false;
              seen.add(key);
              return true;
            });
          }
          applied.push(raw.op);
        }
        d.rows = rows;
        d.cleaned = true;
        return {
          dataset_id: d.dataset_id,
          rows_before: before,
          rows_after: rows.length,
          shape: [rows.length, d.columns.length],
          columns: d.columns,
          dtypes: d.dtypes,
          operations_applied: applied,
          preview: rows.slice(0, 50),
        };
      }
      case 'data.analyze_data': {
        const d = this.dataset(params);
        const analyses = params['analyses'];
        if (!Array.isArray(analyses) || analyses.length === 0) {
          throw new BridgeRpcError({ code: -32602, message: 'analyses must be a non-empty list' });
        }
        return {
          dataset_id: d.dataset_id,
          results: (analyses as { kind: string }[]).map((analysis) =>
            analysis.kind === 'correlation'
              ? {
                  kind: 'correlation',
                  status: 'ok',
                  columns: ['price', 'quantity', 'revenue'],
                  matrix: [
                    [1.0, 0.01, 0.71],
                    [0.01, 1.0, 0.62],
                    [0.71, 0.62, 1.0],
                  ],
                }
              : { kind: analysis.kind, status: 'ok', note: 'echo transport fixture' },
          ),
        };
      }
      case 'data.auto_chart': {
        const d = this.dataset(params);
        return {
          dataset_id: d.dataset_id,
          charts: [
            {
              ...SEED_CHART_SPEC,
              dataset_id: d.dataset_id,
              score: 0.9,
              reason: 'revenue by region (4 groups)',
            },
            {
              type: 'line',
              dataset_id: d.dataset_id,
              x: 'invoice_date',
              y: 'revenue',
              theme: 'default',
              palette: 'viridis',
              score: 0.95,
              reason: 'revenue over time (invoice_date)',
            },
            {
              type: 'scatter',
              dataset_id: d.dataset_id,
              x: 'price',
              y: 'quantity',
              theme: 'default',
              palette: 'viridis',
              score: 0.75,
              reason: 'price vs quantity',
            },
          ].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
        };
      }
      case 'data.create_chart': {
        const spec = params['chart_spec'] as ChartSpecDto | undefined;
        if (!spec || typeof spec !== 'object') {
          throw new BridgeRpcError({ code: -32602, message: 'chart_spec must be an object' });
        }
        const d = this.dataset({ dataset_id: spec.dataset_id });
        this.chartCounter += 1;
        const chartId = `echo-chart-${String(this.chartCounter + 1).padStart(2, '0')}`;
        const chart: ChartResultDto = {
          chart_id: chartId,
          dataset_id: d.dataset_id,
          spec,
          files: {
            png: `${d.dataset_id}/charts/${chartId}.png`,
            svg: `${d.dataset_id}/charts/${chartId}.svg`,
            pdf: `${d.dataset_id}/charts/${chartId}.pdf`,
            html: `${d.dataset_id}/charts/${chartId}.html`,
          },
          sizes: { png: 20480, svg: 16384, pdf: 14336, html: 2048 },
        };
        d.charts.push(chart);
        return chart;
      }
      case 'data.generate_report': {
        const d = this.dataset(params);
        const title = requireString(params, 'title');
        d.reportMarkdown = SEED_REPORT_MARKDOWN.replace('Sales 2024 Annual Review', title);
        return {
          dataset_id: d.dataset_id,
          title,
          pdf_path: `${d.dataset_id}/report.pdf`,
          markdown_path: `${d.dataset_id}/report.md`,
          size_bytes: 38211,
          sections: [
            'abstract',
            'data_summary',
            'methodology',
            'results',
            'discussion',
            'conclusion',
            'references',
          ],
          charts_embedded: Math.min(d.charts.length, 6),
        };
      }
      case 'data.get_report': {
        const d = this.dataset(params);
        return { dataset_id: d.dataset_id, markdown: d.reportMarkdown };
      }
      case 'data.delete_dataset': {
        const d = this.dataset(params);
        this.datasets.delete(d.dataset_id);
        return { deleted: true, dataset_id: d.dataset_id };
      }
      case 'notebook.create': {
        const d = this.dataset(params);
        const name = requireString(params, 'name').replace(/\s+/g, '_');
        const cells = (params['cells'] as { type: string; source: string }[] | undefined) ?? [];
        const path = `${d.dataset_id}/notebooks/${name}.ipynb`;
        d.notebooks.set(
          path,
          cells.map((cell) => ({
            cell_type: cell.type === 'markdown' ? 'markdown' : 'code',
            source: cell.source,
            ...(cell.type === 'markdown' ? {} : { outputs: [], execution_count: null }),
          })),
        );
        return {
          notebook_path: path,
          dataset_id: d.dataset_id,
          name,
          cell_count: cells.length,
        };
      }
      case 'notebook.read': {
        const path = requireString(params, 'path');
        const cells = this.findNotebook(path);
        return { notebook_path: path, cells };
      }
      case 'notebook.execute': {
        const path = requireString(params, 'path');
        const cells = this.findNotebook(path);
        const outputs: { cell_index: number; outputs: unknown[] }[] = [];
        cells.forEach((cell, index) => {
          if (cell.cell_type !== 'code') return;
          cell.execution_count = index + 1;
          cell.outputs = [{ type: 'stream', name: 'stdout', text: `echo: executed cell ${index}` }];
          outputs.push({ cell_index: index, outputs: cell.outputs });
        });
        return {
          notebook_path: path,
          kernel_id: 'echo-kernel',
          cells_executed: outputs.length,
          outputs,
        };
      }
      case 'notebook.run_cell': {
        const path = requireString(params, 'path');
        const cellIndex = params['cell_index'];
        if (typeof cellIndex !== 'number' || cellIndex < 0) {
          throw new BridgeRpcError({
            code: -32602,
            message: 'cell_index must be a non-negative integer',
          });
        }
        const cells = this.findNotebook(path);
        if (cellIndex >= cells.length) {
          throw new BridgeRpcError({ code: -32602, message: 'cell_index out of range' });
        }
        const cell = cells[cellIndex];
        if (cell.cell_type !== 'code') {
          return { notebook_path: path, cell_index: cellIndex, cell_type: 'markdown', outputs: [] };
        }
        cell.execution_count = (cell.execution_count ?? 0) + 1;
        cell.outputs = [
          { type: 'stream', name: 'stdout', text: `echo: executed cell ${cellIndex}` },
        ];
        return {
          notebook_path: path,
          cell_index: cellIndex,
          cell_type: 'code',
          execution_count: cell.execution_count,
          outputs: cell.outputs,
        };
      }
      case 'notebook.open_lab':
        return { url: 'http://127.0.0.1:8890/lab?token=echo', already_running: false };
      default:
        throw new BridgeRpcError({ code: -32601, message: `echo: unknown method ${method}` });
    }
  }

  private findNotebook(path: string): NotebookCellDto[] {
    for (const dataset of this.datasets.values()) {
      const cells = dataset.notebooks.get(path);
      if (cells) return cells;
    }
    throw new BridgeRpcError({ code: -32602, message: `notebook not found: ${path}` });
  }
}

function buildHistogram(values: number[]): { counts: number[]; edges: number[] } {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const bins = 10;
  const width = (max - min) / bins || 1;
  const counts = new Array<number>(bins).fill(0);
  for (const value of values) {
    const bin = Math.min(bins - 1, Math.floor((value - min) / width));
    counts[bin] += 1;
  }
  const edges = Array.from({ length: bins + 1 }, (_, i) => min + i * width);
  return { counts, edges };
}
