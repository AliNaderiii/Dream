/**
 * Typed wrappers for the `data.*` and `notebook.*` RPC families (P-09).
 *
 * Mirrors the validation the sidecar performs in
 * `dream/skills/data_science.py` so obviously bad input never leaves the
 * renderer, but the server remains the authority. Also hosts the pure
 * client-side helpers the workbench UI shares: table sorting/filtering
 * reduce logic and chart-gallery grouping.
 */

import type { BridgeClient } from './client';
import type {
  AnalysisRequestDto,
  AnalysisResultDto,
  ChartResultDto,
  ChartSpecDto,
  CleanOpDto,
  CleanResultDto,
  DatasetDto,
  DatasetProfileDto,
  DatasetSummaryDto,
  NotebookDocumentDto,
  NotebookRefDto,
  NotebookRunResultDto,
  ReportResultDto,
} from './types';

/** Column names the pipeline accepts anywhere (mirrors COLUMN_NAME_RE). */
export const COLUMN_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Chart types the sidecar can render. */
export const CHART_TYPES = [
  'line',
  'bar',
  'scatter',
  'histogram',
  'box',
  'heatmap',
  'pie',
  'area',
  'bubble',
] as const;

/** Themes accepted by `data.create_chart`. */
export const CHART_THEMES = ['default', 'minimal', 'dark', 'ggplot', 'seaborn'] as const;

/** Palettes accepted by `data.create_chart` (strict allowlist). */
export const CHART_PALETTES = [
  'viridis',
  'plasma',
  'inferno',
  'Set1',
  'Set2',
  'Pastel1',
  'custom',
] as const;

/** Validate a column name client-side. Returns an error message or null. */
export function validateColumnName(name: string): string | null {
  if (!COLUMN_NAME_RE.test(name)) {
    return 'Column names must start with a letter or underscore and use only letters, digits, and underscores.';
  }
  if (name.length > 64) return 'Column names must be at most 64 characters.';
  return null;
}

/** Drops `undefined`/`null` entries so the RPC params stay minimal. */
function compact(params: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) out[key] = value;
  }
  return out;
}

// --------------------------------------------------------------------------- //
// data.* wrappers
// --------------------------------------------------------------------------- //

export function loadDataset(
  client: BridgeClient,
  filePath: string,
  name?: string,
): Promise<DatasetDto> {
  if (!filePath.trim()) return Promise.reject(new Error('file path must not be empty'));
  return client.call<DatasetDto>('data.load_data', compact({ file_path: filePath, name }));
}

export function listDatasets(client: BridgeClient): Promise<{ datasets: DatasetSummaryDto[] }> {
  return client.call('data.list_datasets', {});
}

export function getDataset(client: BridgeClient, datasetId: string): Promise<DatasetSummaryDto> {
  return client.call('data.get_dataset', { dataset_id: datasetId });
}

export function deleteDataset(
  client: BridgeClient,
  datasetId: string,
): Promise<{ deleted: boolean; dataset_id: string }> {
  return client.call('data.delete_dataset', { dataset_id: datasetId });
}

export function profileDataset(
  client: BridgeClient,
  datasetId: string,
  maxCategories = 20,
): Promise<DatasetProfileDto> {
  return client.call('data.profile_data', {
    dataset_id: datasetId,
    max_categories: maxCategories,
  });
}

export function cleanDataset(
  client: BridgeClient,
  datasetId: string,
  operations: CleanOpDto[],
): Promise<CleanResultDto> {
  if (operations.length === 0) return Promise.reject(new Error('no operations given'));
  return client.call('data.clean_data', { dataset_id: datasetId, operations });
}

export function analyzeDataset(
  client: BridgeClient,
  datasetId: string,
  analyses: AnalysisRequestDto[],
): Promise<{ dataset_id: string; results: AnalysisResultDto[] }> {
  if (analyses.length === 0) return Promise.reject(new Error('no analyses given'));
  return client.call('data.analyze_data', { dataset_id: datasetId, analyses });
}

export function suggestCharts(
  client: BridgeClient,
  datasetId: string,
  maxCharts = 6,
): Promise<{ dataset_id: string; charts: ChartSpecDto[] }> {
  return client.call('data.auto_chart', { dataset_id: datasetId, max_charts: maxCharts });
}

export function createChart(client: BridgeClient, spec: ChartSpecDto): Promise<ChartResultDto> {
  return client.call('data.create_chart', { chart_spec: spec });
}

export function generateReport(
  client: BridgeClient,
  datasetId: string,
  title: string,
  sections?: string[],
): Promise<ReportResultDto> {
  if (!title.trim()) return Promise.reject(new Error('title must not be empty'));
  return client.call('data.generate_report', compact({ dataset_id: datasetId, title, sections }));
}

export function getReportMarkdown(
  client: BridgeClient,
  datasetId: string,
): Promise<{ dataset_id: string; markdown: string | null }> {
  return client.call('data.get_report', { dataset_id: datasetId });
}

// --------------------------------------------------------------------------- //
// notebook.* wrappers
// --------------------------------------------------------------------------- //

export function createNotebook(
  client: BridgeClient,
  datasetId: string,
  name: string,
  cells: { type: 'code' | 'markdown'; source: string }[],
): Promise<NotebookRefDto> {
  return client.call('notebook.create', { dataset_id: datasetId, name, cells });
}

export function readNotebook(client: BridgeClient, path: string): Promise<NotebookDocumentDto> {
  return client.call('notebook.read', { path });
}

export function executeNotebook(
  client: BridgeClient,
  path: string,
  kernelId?: string,
): Promise<NotebookRunResultDto> {
  return client.call('notebook.execute', compact({ path, kernel_id: kernelId }));
}

export function runNotebookCell(
  client: BridgeClient,
  path: string,
  cellIndex: number,
): Promise<NotebookRunResultDto> {
  return client.call('notebook.run_cell', { path, cell_index: cellIndex });
}

export function openJupyterLab(
  client: BridgeClient,
  path: string,
): Promise<{ url: string; already_running: boolean }> {
  return client.call('notebook.open_lab', { path });
}

// --------------------------------------------------------------------------- //
// Pure table reduce logic (shared by the preview grid and its tests)
// --------------------------------------------------------------------------- //

export type SortDirection = 'asc' | 'desc';

export interface TableQuery {
  /** Case-insensitive substring match across all cells. */
  filter: string;
  sortColumn: string | null;
  sortDirection: SortDirection;
  page: number;
  pageSize: number;
}

export const DEFAULT_TABLE_QUERY: TableQuery = {
  filter: '',
  sortColumn: null,
  sortDirection: 'asc',
  page: 0,
  pageSize: 25,
};

/** Stringify a cell value without `[object Object]` surprises. */
function cellText(value: unknown): string {
  if (value === null || value === undefined) return '';
  switch (typeof value) {
    case 'string':
      return value;
    case 'number':
    case 'boolean':
    case 'bigint':
      return value.toString();
    default:
      return JSON.stringify(value) ?? '';
  }
}

/** Compare two cell values: numbers numerically, everything else as text. */
export function compareCells(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1; // nulls sort last
  if (b == null) return -1;
  const na = typeof a === 'number' ? a : Number(a);
  const nb = typeof b === 'number' ? b : Number(b);
  if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
  return cellText(a).localeCompare(cellText(b));
}

export interface TableView {
  rows: Record<string, unknown>[];
  totalRows: number;
  pageCount: number;
  page: number;
}

/** Filter → sort → paginate, deterministically. */
export function applyTableQuery(rows: Record<string, unknown>[], query: TableQuery): TableView {
  let view = rows;
  const needle = query.filter.trim().toLowerCase();
  if (needle) {
    view = view.filter((row) =>
      Object.values(row).some((value) => cellText(value).toLowerCase().includes(needle)),
    );
  }
  if (query.sortColumn) {
    const column = query.sortColumn;
    const factor = query.sortDirection === 'desc' ? -1 : 1;
    view = [...view].sort((a, b) => factor * compareCells(a[column], b[column]));
  }
  const totalRows = view.length;
  const pageCount = Math.max(1, Math.ceil(totalRows / query.pageSize));
  const page = Math.min(query.page, pageCount - 1);
  const start = page * query.pageSize;
  return { rows: view.slice(start, start + query.pageSize), totalRows, pageCount, page };
}

/** Format a cell for display: nulls become an em-dash, objects JSON. */
export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  return cellText(value);
}

/** Human-readable byte size. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// --------------------------------------------------------------------------- //
// Chart gallery reduce logic
// --------------------------------------------------------------------------- //

/** Group chart results newest-first, deduplicated by chart id. */
export function reduceChartGallery(charts: ChartResultDto[]): ChartResultDto[] {
  const seen = new Set<string>();
  const out: ChartResultDto[] = [];
  for (let i = charts.length - 1; i >= 0; i -= 1) {
    const chart = charts[i];
    if (seen.has(chart.chart_id)) continue;
    seen.add(chart.chart_id);
    out.push(chart);
  }
  return out;
}

/** Pick the best downloadable file for a chart, preferring vector formats. */
export function preferredDownload(chart: ChartResultDto): { format: string; path: string } | null {
  for (const format of ['svg', 'pdf', 'png', 'html'] as const) {
    const path = chart.files[format];
    if (path) return { format, path };
  }
  return null;
}
