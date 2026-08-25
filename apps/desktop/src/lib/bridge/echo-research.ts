/**
 * Deterministic echo runtime for the `research.*` family (P2).
 *
 * Implements the same 11 methods and JSON shapes as P1
 * (`dream/bridge/methods_research.py` + `dream/research/schemas.py`)
 * so the UI has one code path whether running against the sidecar or offline.
 *
 * Seeded with a COMPLETE session whose plan.sections match P1, whose events
 * use P1 event names, and whose report has a markdown_path.
 */

import type {
  CostEstimate,
  Finding,
  Iteration,
  ListSummary,
  Observation,
  Plan,
  ReportRef,
  ResearchConfig,
  ResearchCreateParams,
  ResearchEvent,
  Section,
  SessionRecord,
  SessionSummary,
  ToolCallRecord,
} from './research-types';

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //

function newId(): string {
  return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
}

function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

const BASE_TS = Date.UTC(2026, 7, 24, 10, 0, 0) / 1000; // epoch seconds

// --------------------------------------------------------------------------- //
// Seed data — matches P1 shapes exactly
// --------------------------------------------------------------------------- //

const SEED_CONFIG: ResearchConfig = {
  max_iterations: 3,
  max_time_seconds: 900,
  step_timeout_seconds: 120,
  max_retries: 2,
  max_sections: 6,
  language: 'en',
  autonomous: false,
  allow_network: false,
  max_pages: 20,
  output_length: 'standard',
};

function seedIterations(sectionId: string, _random: () => number): Iteration[] {
  const gap = `What drives ${sectionId === 'sec-exec' ? 'the headline result' : 'this section thesis'}?`;
  const tool: ToolCallRecord = {
    tool: 'data.query',
    arguments: { sql: `SELECT * FROM events WHERE section = '${sectionId}'` },
    ok: true,
    error: '',
    summary: '312 rows returned',
    elapsed_seconds: 1.8,
  };
  const obs: Observation = {
    stdout: 'Analysis complete.\nHazard ratio = 2.31 (CI 1.8–2.9, p<0.001)',
    stderr: '',
    result: { hazard_ratio: 2.31, p_value: 0.001 },
    facts: ['Step-3 errors correlate with 2.3× churn'],
    error: '',
    converged: true,
  };
  return [
    {
      index: 0,
      knowledge_gap: gap,
      tool_calls: [tool],
      code: 'import pandas as pd\ndf = pd.read_csv("events.csv")\nprint(df.describe())',
      observation: obs,
      reflection: 'The data confirms the hypothesis.',
      retries: 0,
      started_at: BASE_TS + 30,
      elapsed_seconds: 11.2,
    },
  ];
}

function seedFindings(sectionId: string): Finding[] {
  return [
    {
      claim: 'Users who encounter >2 errors in step 3 churn at 2.3× the base rate.',
      evidence: 'Hazard ratio = 2.31 (CI 1.8–2.9, p<0.001)',
      metric: 'hazard_ratio',
      value: 2.31,
      kind: 'observation',
      section_id: sectionId,
      iteration: 0,
      grounded: true,
    },
  ];
}

function seedSections(): Section[] {
  const random = makeRandom(20260824);
  return [
    {
      section_id: 'sec-data',
      title: 'Data Overview',
      thesis: 'Understand the dataset shape, coverage, and quality.',
      questions: ['What columns exist?', 'How much data is missing?'],
      status: 'DONE',
      iterations: seedIterations('sec-data', random),
      findings: seedFindings('sec-data'),
      charts: [],
      tables: [{ header: ['Column', 'Type', 'Missing'], rows: [['price', 'float64', '3.2%']] }],
      prose:
        'The dataset contains 1,000 rows across 7 columns. The price column has 3.2% missing values.',
      rationale: '',
      editable: true,
    },
    {
      section_id: 'sec-churn',
      title: 'Churn Analysis',
      thesis: 'Quantify the relationship between onboarding friction and churn.',
      questions: [
        'What is the causal relationship between step-3 errors and churn?',
        'Which onboarding step contributes most to attrition?',
      ],
      status: 'DONE',
      iterations: seedIterations('sec-churn', random),
      findings: seedFindings('sec-churn'),
      charts: ['survival_curve.png'],
      tables: [],
      prose:
        'Kaplan-Meier survival analysis reveals a hazard ratio of 2.31 for users with >2 step-3 errors (p<0.001). Step 3 is the primary attrition point with 31.1% drop-off.',
      rationale: '',
      editable: true,
    },
    {
      section_id: 'sec-revenue',
      title: 'Revenue Impact',
      thesis: 'Model the financial impact of reducing onboarding friction.',
      questions: ['Can we quantify the revenue impact of a 10% reduction in step-3 drop-off?'],
      status: 'DONE',
      iterations: seedIterations('sec-revenue', random),
      findings: [
        {
          claim: 'A simplified onboarding flow recovers ~$18k/mo in projected LTV.',
          evidence: '$18,200/mo (midpoint of $14k–$22k range)',
          metric: 'monthly_ltv_recovery',
          value: 18200,
          kind: 'recommendation',
          section_id: 'sec-revenue',
          iteration: 0,
          grounded: true,
        },
      ],
      charts: ['revenue_projection.png'],
      tables: [
        {
          header: ['Scenario', 'Drop Reduction', 'Monthly LTV Recovery'],
          rows: [
            ['Conservative', '5%', '$9,100'],
            ['Moderate', '10%', '$18,200'],
            ['Aggressive', '20%', '$36,400'],
          ],
        },
      ],
      prose:
        'Three scenarios modelled. A 10% reduction in step-3 drop-off recovers approximately $18,200/month in projected lifetime value.',
      rationale: '',
      editable: true,
    },
    {
      section_id: 'sec-recs',
      title: 'Recommendations',
      thesis: 'Actionable steps to reduce onboarding friction.',
      questions: ['What specific changes will have the most impact?'],
      status: 'DONE',
      iterations: seedIterations('sec-recs', random),
      findings: [
        {
          claim: 'Replacing the free-text field with a dropdown will reduce step-3 time by 40%.',
          evidence: 'Median step-3 time: 94s → estimated 56s with dropdown (−40.4%)',
          metric: 'time_reduction',
          value: 0.404,
          kind: 'recommendation',
          section_id: 'sec-recs',
          iteration: 0,
          grounded: true,
        },
      ],
      charts: [],
      tables: [],
      prose:
        '1. Replace free-text with dropdown. 2. Add inline error recovery. 3. Implement skip for returning users. 4. A/B test the simplified flow.',
      rationale: '',
      editable: true,
    },
  ];
}

function seedEvents(): ResearchEvent[] {
  return [
    {
      event: 'created',
      ts: BASE_TS,
      topic: 'Customer churn & onboarding friction',
      workspace: '/workspace/research',
    },
    { event: 'discovery.start', ts: BASE_TS + 1, workspace: '/workspace/research' },
    { event: 'discovery.done', ts: BASE_TS + 5, datasets: 1, files: 3 },
    { event: 'plan.start', ts: BASE_TS + 6, sources: 1 },
    { event: 'plan.done', ts: BASE_TS + 15, sections: 4, revision: 1 },
    { event: 'plan.approved', ts: BASE_TS + 120, revision: 1 },
    { event: 'section.start', ts: BASE_TS + 121, section: 'Data Overview', dataset_id: 'ds-001' },
    { event: 'section.end', ts: BASE_TS + 132, section: 'Data Overview', status: 'DONE' },
    { event: 'section.start', ts: BASE_TS + 133, section: 'Churn Analysis', dataset_id: 'ds-001' },
    { event: 'section.end', ts: BASE_TS + 159, section: 'Churn Analysis', status: 'DONE' },
    { event: 'section.start', ts: BASE_TS + 160, section: 'Revenue Impact', dataset_id: 'ds-001' },
    { event: 'section.end', ts: BASE_TS + 179, section: 'Revenue Impact', status: 'DONE' },
    { event: 'section.start', ts: BASE_TS + 180, section: 'Recommendations', dataset_id: 'ds-001' },
    { event: 'section.end', ts: BASE_TS + 194, section: 'Recommendations', status: 'DONE' },
    { event: 'proofread.done', ts: BASE_TS + 200, redactions: 0, ok: true },
    { event: 'report.compiled', ts: BASE_TS + 210, pages: 8, chars: 4200 },
  ];
}

function seedCostEstimate(): CostEstimate {
  return {
    sections: 4,
    max_iterations: 3,
    estimated_model_calls: 41,
    estimated_tokens: 36900,
    estimated_sandbox_runs: 12,
    max_wall_clock_seconds: 900,
    backend: 'EchoBackend',
  };
}

function seedReport(): ReportRef {
  return {
    markdown_path: '/workspace/research/report.md',
    pdf_path: '/workspace/research/report.pdf',
    bundle_path: '/workspace/research/report-bundle.zip',
    record_ids: ['sec-data', 'sec-churn', 'sec-revenue', 'sec-recs'],
    pages: 8,
    proofread: { ok: true, redactions: 0 },
  };
}

const SEED_MARKDOWN = `# Customer Churn & Onboarding Friction Analysis

## Executive Summary

This report analyses the causal relationship between onboarding friction and customer churn
using the 2024 sales dataset (n=1,000). Key finding: **users who encounter >2 errors in
step 3 churn at 2.3× the base rate**, and a simplified onboarding flow could recover
approximately **$18,200/month** in projected lifetime value.

## Data Overview

The dataset contains 1,000 rows across 7 columns. The price column has 3.2% missing values.

| Column | Type | Missing |
|--------|------|---------|
| invoice_date | date | 0% |
| region | categorical | 0% |
| product | categorical | 0% |
| price | float | 3.2% |
| quantity | int | 0% |
| revenue | float | 0% |
| email | string | 5.0% |

## Churn Analysis

Kaplan-Meier survival analysis reveals a hazard ratio of **2.31** for users with >2 step-3
errors (CI 1.8–2.9, p<0.001). Step 3 is the primary attrition point with 31.1% drop-off.

\`\`\`python
from lifelines import KaplanMeierFitter
kmf = KaplanMeierFitter()
kmf.fit(durations, event_observed, group="error_count")
kmf.plot()
\`\`\`

## Revenue Impact

Three scenarios modelled:

| Scenario | Step-3 Drop Reduction | Monthly LTV Recovery |
|----------|----------------------|---------------------|
| Conservative | 5% | $9,100 |
| **Moderate** | **10%** | **$18,200** |
| Aggressive | 20% | $36,400 |

## Recommendations

1. **Replace the free-text field in step 3 with a dropdown** — projected 40% time reduction.
2. **Add inline error recovery** — auto-suggest fixes for the top 3 validation errors.
3. **Implement a skip option** for returning users.
4. **A/B test the simplified flow** — validate the 2.3× churn hypothesis with live traffic.
`;

// --------------------------------------------------------------------------- //
// In-memory store
// --------------------------------------------------------------------------- //

const SEED_SESSION_ID = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6';

interface StoredSession {
  record: SessionRecord;
}

const sessions = new Map<string, StoredSession>();

function buildSummary(record: SessionRecord): SessionSummary {
  const done = record.plan.sections.filter(
    (s) => s.status === 'DONE' || s.status === 'SKIPPED' || s.status === 'FAILED',
  ).length;
  return {
    session_id: record.session_id,
    status: record.status,
    topic: record.topic,
    sections_total: record.plan.sections.length,
    sections_done: done,
    progress:
      record.plan.sections.length > 0
        ? Math.round((done / record.plan.sections.length) * 1000) / 1000
        : 0,
    events: record.events.length,
    error: record.error,
    published: record.published,
    report: record.report,
    cost_estimate: record.cost_estimate,
  };
}

function buildListSummary(record: SessionRecord): ListSummary {
  return {
    session_id: record.session_id,
    topic: record.topic,
    status: record.status,
    sections: record.plan.sections.length,
    created_at: record.created_at,
    updated_at: record.updated_at,
    published: record.published,
    report: record.report.markdown_path,
  };
}

function seedCompleteSession(): StoredSession {
  const sections = seedSections();
  const plan: Plan = {
    objective:
      'Analyse the causal relationship between onboarding step-3 errors and first-month churn.',
    questions: [
      'What is the causal relationship between customer churn and onboarding friction?',
      'Which onboarding step contributes most to first-week attrition?',
      'Can we quantify the revenue impact of a 10% reduction in step-3 drop-off?',
    ],
    hypotheses: [
      'Users who encounter >2 errors in step 3 churn at 2.3× the base rate.',
      'Replacing the free-text field with a dropdown will reduce step-3 time by 40%.',
      'A simplified onboarding flow recovers ~$18k/mo in projected LTV.',
    ],
    methodology:
      'Mixed-methods: quantitative survival analysis on the events table, qualitative review of support tickets (n=120), and an A/B projection model.',
    sections,
    datasets: ['ds-001'],
    revision: 1,
    approved: true,
    source: 'model',
  };
  const record: SessionRecord = {
    session_id: SEED_SESSION_ID,
    topic: 'Customer churn & onboarding friction',
    workspace: '/workspace/research',
    status: 'COMPLETE',
    config: SEED_CONFIG,
    plan,
    sources: [{ kind: 'dataset', name: 'Sales 2024', dataset_id: 'ds-001' }],
    report: seedReport(),
    events: seedEvents(),
    error: '',
    created_at: BASE_TS,
    updated_at: BASE_TS + 210,
    cost_estimate: seedCostEstimate(),
    published: false,
  };
  return { record };
}

// Pre-seed on module load
sessions.set(SEED_SESSION_ID, seedCompleteSession());

// --------------------------------------------------------------------------- //
// Public API — mirrors the 11 P1 handlers exactly
// --------------------------------------------------------------------------- //

function getSession(sessionId: string): StoredSession {
  const s = sessions.get(sessionId);
  if (!s) throw new Error(`research session not found: ${sessionId}`);
  return s;
}

/** `research.create` */
export function echoCreate(params: ResearchCreateParams): SessionSummary {
  const sessionId = newId();
  const now = Date.now() / 1000;
  const config: ResearchConfig = { ...SEED_CONFIG, ...params.config };
  const record: SessionRecord = {
    session_id: sessionId,
    topic: params.topic,
    workspace: params.workspace,
    status: 'IDLE',
    config,
    plan: {
      objective: '',
      questions: [],
      hypotheses: [],
      methodology: '',
      sections: [],
      datasets: [],
      revision: 0,
      approved: false,
      source: 'model',
    },
    sources: [],
    report: {
      markdown_path: '',
      pdf_path: '',
      bundle_path: '',
      record_ids: [],
      pages: 0,
      proofread: {},
    },
    events: [{ event: 'created', ts: now, topic: params.topic, workspace: params.workspace }],
    error: '',
    created_at: now,
    updated_at: now,
    cost_estimate: {
      sections: 0,
      max_iterations: config.max_iterations,
      estimated_model_calls: 0,
      estimated_tokens: 0,
      estimated_sandbox_runs: 0,
      max_wall_clock_seconds: config.max_time_seconds,
      backend: 'EchoBackend',
    },
    published: false,
  };
  sessions.set(sessionId, { record });
  return buildSummary(record);
}

/** `research.list` */
export function echoList(): { sessions: ListSummary[]; count: number } {
  const list = [...sessions.values()]
    .map((s) => buildListSummary(s.record))
    .sort((a, b) => b.updated_at - a.updated_at);
  return { sessions: list, count: list.length };
}

/** `research.get` */
export function echoGet(sessionId: string): SessionRecord {
  return getSession(sessionId).record;
}

/** `research.plan` */
export function echoPlan(sessionId: string): SessionSummary & { plan: Plan } {
  const stored = getSession(sessionId);
  const r = stored.record;
  // Simulate plan generation
  const sections = seedSections();
  r.plan = {
    objective:
      'Analyse the causal relationship between onboarding step-3 errors and first-month churn.',
    questions: [
      'What is the causal relationship between customer churn and onboarding friction?',
      'Which onboarding step contributes most to first-week attrition?',
    ],
    hypotheses: [
      'Users who encounter >2 errors in step 3 churn at 2.3× the base rate.',
      'A simplified onboarding flow recovers ~$18k/mo in projected LTV.',
    ],
    methodology:
      'Mixed-methods: quantitative survival analysis, qualitative review, and A/B projection.',
    sections,
    datasets: ['ds-001'],
    revision: r.plan.revision + 1,
    approved: false,
    source: 'model',
  };
  r.status = 'APPROVAL_PENDING';
  r.cost_estimate = seedCostEstimate();
  r.events.push({ event: 'plan.start', ts: Date.now() / 1000, sources: 1 });
  r.events.push({
    event: 'plan.done',
    ts: Date.now() / 1000,
    sections: sections.length,
    revision: r.plan.revision,
  });
  r.updated_at = Date.now() / 1000;
  return { ...buildSummary(r), plan: r.plan };
}

/** `research.approve` */
export function echoApprove(sessionId: string): SessionSummary & { plan: Plan } {
  const stored = getSession(sessionId);
  const r = stored.record;
  if (r.status !== 'APPROVAL_PENDING') {
    throw new Error(`nothing to approve: the session is ${r.status}`);
  }
  r.plan.approved = true;
  r.events.push({ event: 'plan.approved', ts: Date.now() / 1000, revision: r.plan.revision });
  r.updated_at = Date.now() / 1000;
  return { ...buildSummary(r), plan: r.plan };
}

/** `research.modify` */
export function echoModify(
  sessionId: string,
  changes: Record<string, unknown>,
): SessionSummary & { plan: Plan } {
  const stored = getSession(sessionId);
  const r = stored.record;
  if (changes.replan === true) {
    // Re-plan: reset sections
    r.plan.sections = [];
    r.plan.approved = false;
    r.plan.revision += 1;
  } else if (changes.sections && Array.isArray(changes.sections)) {
    // Edit sections
    for (const edit of changes.sections as {
      section_id?: string;
      title?: string;
      thesis?: string;
    }[]) {
      const section = r.plan.sections.find((s) => s.section_id === edit.section_id);
      if (section) {
        if (edit.title) section.title = edit.title;
        if (edit.thesis) section.thesis = edit.thesis;
      }
    }
    r.plan.approved = false;
    r.plan.revision += 1;
  }
  r.events.push({ event: 'plan.modified', ts: Date.now() / 1000, revision: r.plan.revision });
  r.updated_at = Date.now() / 1000;
  return { ...buildSummary(r), plan: r.plan };
}

/** `research.start` — simulates execution to COMPLETE. */
export function echoStart(sessionId: string): SessionSummary {
  const stored = getSession(sessionId);
  const r = stored.record;
  if (!r.plan.approved && !r.config.autonomous) {
    throw new Error('the plan must be approved before an interactive run starts');
  }
  r.status = 'IN_PROGRESS';
  r.updated_at = Date.now() / 1000;
  // Simulate immediate completion for echo
  for (const section of r.plan.sections) {
    r.events.push({ event: 'section.start', ts: Date.now() / 1000, section: section.title });
    section.status = 'DONE';
    r.events.push({
      event: 'section.end',
      ts: Date.now() / 1000,
      section: section.title,
      status: 'DONE',
    });
  }
  r.events.push({ event: 'proofread.done', ts: Date.now() / 1000, redactions: 0, ok: true });
  r.events.push({ event: 'report.compiled', ts: Date.now() / 1000, pages: 8, chars: 4200 });
  r.report = seedReport();
  r.status = 'COMPLETE';
  r.updated_at = Date.now() / 1000;
  return buildSummary(r);
}

/** `research.status` */
export function echoStatus(
  sessionId: string,
  cursor = 0,
): SessionSummary & { cursor: number; new_events: ResearchEvent[] } {
  const stored = getSession(sessionId);
  const r = stored.record;
  const newEvents = r.events.slice(cursor);
  return {
    ...buildSummary(r),
    cursor: cursor + newEvents.length,
    new_events: newEvents.slice(-200),
  };
}

/** `research.stream` — yields chunks via callback. */
export function echoStream(
  sessionId: string,
  cursor: number,
  onChunk: (chunk: { event: ResearchEvent; cursor: number }) => void,
  _signal?: AbortSignal,
): Promise<SessionSummary> {
  const stored = getSession(sessionId);
  const r = stored.record;
  // Replay events after cursor
  let index = cursor;
  const events = r.events.slice(cursor);
  for (const event of events) {
    index += 1;
    onChunk({ event, cursor: index });
  }
  return Promise.resolve(buildSummary(r));
}

/** `research.stop` */
export function echoStop(sessionId: string): SessionSummary {
  const stored = getSession(sessionId);
  const r = stored.record;
  if (r.status === 'IN_PROGRESS' || r.status === 'PLANNING' || r.status === 'APPROVAL_PENDING') {
    r.status = 'CANCELLED';
    r.events.push({ event: 'cancelled', ts: Date.now() / 1000 });
    r.updated_at = Date.now() / 1000;
  }
  return buildSummary(r);
}

/** `research.export` */
export function echoExport(sessionId: string): SessionSummary & { report: ReportRef } {
  const stored = getSession(sessionId);
  const r = stored.record;
  if (r.status !== 'COMPLETE') {
    throw new Error('only a COMPLETE session can be published');
  }
  r.published = true;
  r.events.push({ event: 'published', ts: Date.now() / 1000 });
  r.updated_at = Date.now() / 1000;
  return { ...buildSummary(r), report: r.report };
}

/** Get the seed markdown (for echo-mode report display). */
export function echoGetMarkdown(): string {
  return SEED_MARKDOWN;
}

/** Get the seed session id (for tests). */
export function getSeedSessionId(): string {
  return SEED_SESSION_ID;
}

/** Reset to seed state (for tests). */
export function resetEchoResearch(): void {
  sessions.clear();
  sessions.set(SEED_SESSION_ID, seedCompleteSession());
}
