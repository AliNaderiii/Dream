import { seedSalesRows } from './echo-data';
import type {
  DataQaAskResult,
  DataQaChart,
  DataQaDiscoveryResult,
  DataQaSession,
  DataQaSessionList,
} from './dataqa';

const sessions = new Map<string, DataQaSession>();
const charts = new Map<string, DataQaChart>();
const rows = seedSalesRows();
let sequence = 1;

const columns = [
  { name: 'invoice_date', dtype: 'datetime', role: 'time', null_count: 0, unique_count: 336 },
  { name: 'region', dtype: 'string', role: 'category', null_count: 0, unique_count: 4 },
  { name: 'product', dtype: 'string', role: 'category', null_count: 0, unique_count: 3 },
  { name: 'price', dtype: 'number', role: 'measure', null_count: 30, unique_count: 800 },
  { name: 'quantity', dtype: 'number', role: 'measure', null_count: 0, unique_count: 9 },
  { name: 'revenue', dtype: 'number', role: 'measure', null_count: 0, unique_count: 900 },
];

function profile() {
  return {
    dataset_id: 'echo-sales-2024',
    name: 'Sales 2024',
    relative_path: 'echo/sales-2024.csv',
    format: 'csv',
    row_count: rows.length,
    sampled_rows: rows.length,
    columns,
    loadable: true,
    injection_findings: 0,
    infobox: { dataset: 'Sales 2024', format: 'csv', rows: rows.length, columns },
  };
}

export function echoDataQaDiscover(query = ''): DataQaDiscoveryResult {
  return {
    query,
    source: 'echo',
    count: 1,
    candidates: [
      {
        dataset_id: 'echo-sales-2024',
        name: 'Sales 2024',
        relative_path: 'echo/sales-2024.csv',
        format: 'csv',
        source: 'echo',
        score: 0.98,
        reasons: ['dataset name and schema match sales, revenue, and region'],
        columns: columns.map((column) => column.name),
        row_count: rows.length,
        loadable: true,
        size_bytes: 64000,
        profile: profile(),
      },
    ],
  };
}

export function echoDataQaCreate(): DataQaSession {
  const id = sequence.toString(16).padStart(32, '0');
  sequence += 1;
  const now = Date.now() / 1000;
  const session: DataQaSession = {
    session_id: id,
    created_at: now,
    updated_at: now,
    turn_count: 0,
    stateful: false,
    dataset: echoDataQaDiscover().candidates[0],
    profile: profile(),
  };
  sessions.set(id, session);
  return session;
}

export function echoDataQaSessions(): DataQaSessionList {
  return { sessions: [...sessions.values()] };
}

export function echoDataQaGet(sessionId: string): DataQaSession {
  const session = sessions.get(sessionId);
  if (!session) throw new Error('Unknown Data Q&A session');
  return session;
}

export function echoDataQaDelete(sessionId: string) {
  charts.delete(sessionId);
  return { deleted: sessions.delete(sessionId), session_id: sessionId };
}

export function echoDataQaAsk(sessionId: string, question: string): DataQaAskResult {
  const session = sessions.get(sessionId);
  if (!session) throw new Error('Unknown Data Q&A session');
  const persian = /[\u0600-\u06ff]/.test(question);
  const grouped = new Map<string, number[]>();
  rows.forEach((row) => {
    const values = grouped.get(row.region) ?? [];
    values.push(row.revenue);
    grouped.set(row.region, values);
  });
  const evidenceRows = [...grouped].map(([region, values]) => ({
    region,
    mean_revenue:
      Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) / 100,
  }));
  const grounded =
    /average|mean|میانگین/.test(question.toLowerCase()) &&
    /region|منطقه/.test(question.toLowerCase());
  const renderedAverages = evidenceRows
    .map((row) => `${row.region}: ${row.mean_revenue.toLocaleString('en-US')}`)
    .join('; ');
  const answer = grounded
    ? persian
      ? `میانگین درآمد به تفکیک منطقه — ${renderedAverages}`
      : `Average revenue by region — ${renderedAverages}`
    : persian
      ? 'از این داده‌ها قابل تعیین نیست.'
      : "I can't determine that from this data.";
  const chart: DataQaChart | null = grounded
    ? {
        type: 'bar',
        format: 'svg',
        validated: true,
        points: 4,
        labels: ['region', 'mean_revenue'],
        consistency: 'rendered from returned evidence rows',
      }
    : null;
  if (chart) charts.set(sessionId, chart);
  else charts.delete(sessionId);
  session.turn_count += 1;
  session.stateful = grounded;
  session.updated_at = Date.now() / 1000;
  return {
    session_id: sessionId,
    final_answer: {
      status: grounded ? 'ok' : 'insufficient_data',
      answer,
      summary: answer,
      language: persian ? 'fa' : 'en',
      grounded: true,
      evidence: {
        dataset: 'Sales 2024',
        schema: profile().infobox,
        columns: grounded ? ['region', 'mean_revenue'] : [],
        rows: grounded ? evidenceRows : [],
        rows_considered: rows.length,
        operation: grounded ? 'aggregate' : 'insufficient',
      },
      plan: {
        action: grounded ? 'aggregate' : 'insufficient',
        aggregate: grounded ? 'mean' : null,
        metric: grounded ? 'revenue' : null,
        groups: grounded ? ['region'] : [],
        intent: grounded ? 'mean revenue by region' : 'not grounded',
      },
      generated_code: grounded
        ? "result = df.groupby(['region'])['revenue'].mean().reset_index()"
        : '',
      chart,
      warnings: [],
      sandbox: { kind: 'echo', network_enabled: false },
    },
  };
}

export function echoDataQaChart(sessionId: string) {
  if (!sessions.has(sessionId)) throw new Error('Unknown Data Q&A session');
  const chart = charts.get(sessionId);
  if (!chart) throw new Error('The latest answer does not support a consistent chart');
  return { session_id: sessionId, chart };
}

export function echoDataQaReset(sessionId: string) {
  const session = sessions.get(sessionId);
  if (!session) throw new Error('Unknown Data Q&A session');
  charts.delete(sessionId);
  session.turn_count = 0;
  session.stateful = false;
  return { session_id: sessionId, reset: true, session };
}
