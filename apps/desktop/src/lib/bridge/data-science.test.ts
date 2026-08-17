/**
 * Unit tests for the data-science wrapper module: RPC wrappers against the
 * echo transport, plus the pure table / gallery reduce logic.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { BridgeClient, EchoBridgeTransport } from './client';
import {
  applyTableQuery,
  cleanDataset,
  compareCells,
  createChart,
  DEFAULT_TABLE_QUERY,
  formatBytes,
  formatCell,
  generateReport,
  getReportMarkdown,
  listDatasets,
  preferredDownload,
  profileDataset,
  reduceChartGallery,
  suggestCharts,
  validateColumnName,
} from './data-science';
import type { ChartResultDto } from './types';

describe('data-science wrappers (echo transport)', () => {
  let client: BridgeClient;

  beforeEach(() => {
    client = new BridgeClient(new EchoBridgeTransport());
  });

  it('lists the seeded sales-2024 dataset', async () => {
    const { datasets } = await listDatasets(client);
    expect(datasets).toHaveLength(1);
    expect(datasets[0].name).toBe('sales-2024');
    expect(datasets[0].shape[0]).toBe(1000);
    expect(datasets[0].columns).toContain('revenue');
  });

  it('is deterministic: two transports seed identical data', async () => {
    const other = new BridgeClient(new EchoBridgeTransport());
    const a = await listDatasets(client);
    const b = await listDatasets(other);
    expect(a).toEqual(b);
    const [pa, pb] = await Promise.all([
      profileDataset(client, a.datasets[0].dataset_id),
      profileDataset(other, b.datasets[0].dataset_id),
    ]);
    expect(pa).toEqual(pb);
  });

  it('profiles the seeded dataset with numeric and categorical columns', async () => {
    const { datasets } = await listDatasets(client);
    const profile = await profileDataset(client, datasets[0].dataset_id);
    expect(profile.row_count).toBe(1000);
    expect(profile.columns['price'].role).toBe('numeric');
    expect(profile.columns['price'].missing).toBeGreaterThan(0);
    expect(profile.columns['region'].role).toBe('categorical');
    expect(profile.columns['region'].top_values?.length).toBeGreaterThan(0);
    expect(profile.columns['price'].histogram?.counts).toHaveLength(10);
  });

  it('cleans the dataset and reports the row delta', async () => {
    const { datasets } = await listDatasets(client);
    const result = await cleanDataset(client, datasets[0].dataset_id, [
      { op: 'drop_na', columns: ['email'] },
    ]);
    expect(result.rows_before).toBe(1000);
    expect(result.rows_after).toBeLessThan(1000);
    expect(result.operations_applied).toEqual(['drop_na']);
  });

  it('suggests ranked charts and renders one', async () => {
    const { datasets } = await listDatasets(client);
    const { charts } = await suggestCharts(client, datasets[0].dataset_id);
    expect(charts.length).toBeGreaterThan(0);
    const scores = charts.map((c) => c.score ?? 0);
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);

    const rendered = await createChart(client, charts[0]);
    expect(rendered.chart_id).toBeTruthy();
    expect(rendered.files.png).toContain(datasets[0].dataset_id);
  });

  it('generates a report and reads its markdown back', async () => {
    const { datasets } = await listDatasets(client);
    const report = await generateReport(client, datasets[0].dataset_id, 'Vitest Report');
    expect(report.pdf_path).toContain('report.pdf');
    const { markdown } = await getReportMarkdown(client, datasets[0].dataset_id);
    expect(markdown).toContain('# Vitest Report');
  });

  it('rejects an unknown dataset id', async () => {
    await expect(profileDataset(client, 'nope')).rejects.toMatchObject({ code: -32602 });
  });

  it('rejects empty client-side inputs before any RPC', async () => {
    await expect(cleanDataset(client, 'x', [])).rejects.toThrow('no operations');
    await expect(generateReport(client, 'x', '   ')).rejects.toThrow('title');
  });
});

describe('validateColumnName', () => {
  it('accepts snake_case identifiers', () => {
    expect(validateColumnName('invoice_date')).toBeNull();
    expect(validateColumnName('_x9')).toBeNull();
  });
  it('rejects injection-shaped names', () => {
    expect(validateColumnName('a; DROP TABLE')).toContain('Column names');
    expect(validateColumnName('9lives')).toContain('Column names');
    expect(validateColumnName('c'.repeat(65))).toContain('64');
  });
});

describe('table reduce logic', () => {
  const rows = [
    { name: 'c', value: 3 },
    { name: 'a', value: 10 },
    { name: 'b', value: null },
  ];

  it('sorts numerically with nulls last', () => {
    const view = applyTableQuery(rows, {
      ...DEFAULT_TABLE_QUERY,
      sortColumn: 'value',
      sortDirection: 'asc',
    });
    expect(view.rows.map((r) => r['name'])).toEqual(['c', 'a', 'b']);
  });

  it('sorts descending by text', () => {
    const view = applyTableQuery(rows, {
      ...DEFAULT_TABLE_QUERY,
      sortColumn: 'name',
      sortDirection: 'desc',
    });
    expect(view.rows.map((r) => r['name'])).toEqual(['c', 'b', 'a']);
  });

  it('filters case-insensitively across all cells', () => {
    const view = applyTableQuery(rows, { ...DEFAULT_TABLE_QUERY, filter: 'A' });
    expect(view.rows).toHaveLength(1);
    expect(view.rows[0]['name']).toBe('a');
  });

  it('paginates and clamps the page index', () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ i }));
    const page1 = applyTableQuery(many, { ...DEFAULT_TABLE_QUERY, pageSize: 25, page: 1 });
    expect(page1.rows).toHaveLength(5);
    expect(page1.pageCount).toBe(2);
    const clamped = applyTableQuery(many, { ...DEFAULT_TABLE_QUERY, pageSize: 25, page: 99 });
    expect(clamped.page).toBe(1);
  });

  it('compareCells handles mixed types', () => {
    expect(compareCells(2, 10)).toBeLessThan(0);
    expect(compareCells('2', '10')).toBeLessThan(0); // numeric strings compare numerically
    expect(compareCells('apple', 'banana')).toBeLessThan(0);
    expect(compareCells(null, 1)).toBeGreaterThan(0); // nulls last
  });

  it('formats cells for display', () => {
    expect(formatCell(null)).toBe('—');
    expect(formatCell('')).toBe('—');
    expect(formatCell(3.5)).toBe('3.5');
    expect(formatCell({ a: 1 })).toBe('{"a":1}');
  });

  it('formats byte sizes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB');
  });
});

describe('chart gallery reduce logic', () => {
  const chart = (id: string): ChartResultDto => ({
    chart_id: id,
    dataset_id: 'd',
    spec: { type: 'bar', dataset_id: 'd', x: 'a', y: 'b' },
    files: { png: `${id}.png`, html: `${id}.html` },
    sizes: { png: 1 },
  });

  it('dedupes by chart id keeping the newest first', () => {
    const out = reduceChartGallery([chart('a'), chart('b'), chart('a')]);
    expect(out.map((c) => c.chart_id)).toEqual(['a', 'b']);
  });

  it('prefers vector formats for download', () => {
    const withSvg: ChartResultDto = {
      ...chart('x'),
      files: { png: 'x.png', svg: 'x.svg', html: 'x.html' },
    };
    expect(preferredDownload(withSvg)).toEqual({ format: 'svg', path: 'x.svg' });
    expect(preferredDownload(chart('y'))).toEqual({ format: 'png', path: 'y.png' });
    expect(preferredDownload({ ...chart('z'), files: {} })).toBeNull();
  });
});
