/**
 * Deterministic echo runtime for the `research.*` family (P2).
 *
 * Mirrors `echo-data.ts`: browser dev and vitest have no sidecar, so the
 * workbench renders against this in-memory model. A realistic multi-section
 * plan, a trace with a couple of self-corrected errors, a final report, and
 * figures are seeded deterministically so the same build always shows the
 * same state.
 */

import type {
  ResearchClaim,
  ResearchCostEstimate,
  ResearchCreateParams,
  ResearchFigure,
  ResearchPlan,
  ResearchProgressEvent,
  ResearchReport,
  ResearchReportSection,
  ResearchSession,
  ResearchStep,
  ResearchToolCall,
} from './research-types';

const SEED_SESSION_ID = 'rsch-a1b2c3d4e5f6789012345678';

/** Deterministic PRNG (LCG) — same seed, same trace, every run. */
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

/** ISO timestamp offset from a base time. */
function isoOffset(baseMs: number, offsetMs: number): string {
  return new Date(baseMs + offsetMs).toISOString();
}

// --------------------------------------------------------------------------- //
// Seed data
// --------------------------------------------------------------------------- //

const BASE_TIME_MS = Date.UTC(2026, 7, 24, 10, 0, 0); // 2026-08-24T10:00Z

const SEED_PLAN: ResearchPlan = {
  research_questions: [
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
  outline: [
    {
      title: 'Executive Summary',
      children: [],
    },
    {
      title: 'Data Overview',
      children: [{ title: 'Sources & Coverage' }, { title: 'Schema Summary' }],
    },
    {
      title: 'Churn Analysis',
      children: [
        { title: 'Survival Curve' },
        { title: 'Step-Level Funnel' },
        { title: 'Error Correlation' },
      ],
    },
    {
      title: 'Revenue Impact',
      children: [{ title: 'LTV Model' }, { title: 'Projection' }],
    },
    {
      title: 'Recommendations',
    },
    {
      title: 'Appendix',
      children: [{ title: 'Reproducibility' }, { title: 'Raw Statistics' }],
    },
  ],
  estimated_cost_usd: 0.42,
  estimated_tokens: 185_000,
};

const SEED_TOOL_CALLS: Record<string, ResearchToolCall[]> = {
  'step-analyze': [
    {
      call_id: 'tc-001',
      tool_name: 'dataset.profile',
      args: { dataset_id: 'ec40da7a-...' },
      result: '7 columns, 1,000 rows, 3.2% missing values in price.',
      risk_tier: 'safe',
      started_at: isoOffset(BASE_TIME_MS, 2_000),
      completed_at: isoOffset(BASE_TIME_MS, 4_500),
    },
  ],
  'step-code-1': [
    {
      call_id: 'tc-002',
      tool_name: 'code.run',
      args: { language: 'python', lines: 42 },
      result: 'OK — wrote churn_curve.png (34 KB)',
      risk_tier: 'caution',
      started_at: isoOffset(BASE_TIME_MS, 30_000),
      completed_at: isoOffset(BASE_TIME_MS, 41_200),
    },
    {
      call_id: 'tc-003',
      tool_name: 'code.run',
      args: { language: 'python', lines: 8 },
      error: "NameError: name 'survfit' is not defined",
      risk_tier: 'caution',
      started_at: isoOffset(BASE_TIME_MS, 42_000),
      completed_at: isoOffset(BASE_TIME_MS, 43_100),
    },
    {
      call_id: 'tc-004',
      tool_name: 'code.run',
      args: { language: 'python', lines: 11 },
      result: 'OK — self-corrected, imported lifelines.survfit.',
      risk_tier: 'caution',
      started_at: isoOffset(BASE_TIME_MS, 44_000),
      completed_at: isoOffset(BASE_TIME_MS, 52_000),
    },
  ],
  'step-execute': [
    {
      call_id: 'tc-005',
      tool_name: 'data.query',
      args: { sql: 'SELECT ... FROM events WHERE step = 3' },
      result: '312 rows returned.',
      risk_tier: 'safe',
      started_at: isoOffset(BASE_TIME_MS, 60_000),
      completed_at: isoOffset(BASE_TIME_MS, 61_800),
    },
  ],
};

const SEED_STEPS: ResearchStep[] = [
  {
    step_id: 'step-analyze',
    session_id: SEED_SESSION_ID,
    phase: 'analyze',
    title: 'Understand the data',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 1_000),
    completed_at: isoOffset(BASE_TIME_MS, 5_000),
    elapsed_ms: 4_000,
    tokens_used: 1_200,
    cost_usd: 0.003,
    output: 'Profiled 1,000-row sales dataset. Found 3.2% missing in price column.',
    tool_calls: SEED_TOOL_CALLS['step-analyze'],
  },
  {
    step_id: 'step-plan',
    session_id: SEED_SESSION_ID,
    phase: 'plan',
    title: 'Formulate research plan',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 6_000),
    completed_at: isoOffset(BASE_TIME_MS, 15_000),
    elapsed_ms: 9_000,
    tokens_used: 3_500,
    cost_usd: 0.012,
    output: 'Generated plan with 3 research questions and 3 hypotheses.',
  },
  {
    step_id: 'step-discover',
    session_id: SEED_SESSION_ID,
    phase: 'discover',
    title: 'Literature & prior art',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 16_000),
    completed_at: isoOffset(BASE_TIME_MS, 28_000),
    elapsed_ms: 12_000,
    tokens_used: 8_200,
    cost_usd: 0.028,
    output: 'Found 4 relevant prior analyses in workspace memory.',
  },
  {
    step_id: 'step-code-1',
    session_id: SEED_SESSION_ID,
    phase: 'code',
    title: 'Survival analysis code',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 29_000),
    completed_at: isoOffset(BASE_TIME_MS, 53_000),
    elapsed_ms: 24_000,
    tokens_used: 6_100,
    cost_usd: 0.021,
    output:
      'Ran survival analysis. Self-corrected a NameError on attempt 2 (imported lifelines.survfit).',
    tool_calls: SEED_TOOL_CALLS['step-code-1'],
  },
  {
    step_id: 'step-execute',
    session_id: SEED_SESSION_ID,
    phase: 'execute',
    title: 'Execute step-3 funnel query',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 54_000),
    completed_at: isoOffset(BASE_TIME_MS, 62_000),
    elapsed_ms: 8_000,
    tokens_used: 900,
    cost_usd: 0.002,
    output: '312 users reached step 3; 97 dropped off (31.1%).',
    tool_calls: SEED_TOOL_CALLS['step-execute'],
  },
  {
    step_id: 'step-observe',
    session_id: SEED_SESSION_ID,
    phase: 'observe',
    title: 'Interpret results',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 63_000),
    completed_at: isoOffset(BASE_TIME_MS, 78_000),
    elapsed_ms: 15_000,
    tokens_used: 4_800,
    cost_usd: 0.016,
    output: 'Step-3 drop-off correlates with 2.3× churn (p<0.01). Hypothesis 1 supported.',
  },
  {
    step_id: 'step-evidence',
    session_id: SEED_SESSION_ID,
    phase: 'evidence',
    title: 'Link claims to evidence',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 79_000),
    completed_at: isoOffset(BASE_TIME_MS, 85_000),
    elapsed_ms: 6_000,
    tokens_used: 2_100,
    cost_usd: 0.007,
    output: 'Linked 6 key claims to their source runs.',
  },
  {
    step_id: 'step-section-exec',
    session_id: SEED_SESSION_ID,
    phase: 'section',
    title: 'Executive Summary',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 86_000),
    completed_at: isoOffset(BASE_TIME_MS, 95_000),
    elapsed_ms: 9_000,
    tokens_used: 3_200,
    cost_usd: 0.011,
  },
  {
    step_id: 'step-section-data',
    session_id: SEED_SESSION_ID,
    phase: 'section',
    title: 'Data Overview',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 96_000),
    completed_at: isoOffset(BASE_TIME_MS, 108_000),
    elapsed_ms: 12_000,
    tokens_used: 4_500,
    cost_usd: 0.015,
  },
  {
    step_id: 'step-section-churn',
    session_id: SEED_SESSION_ID,
    phase: 'section',
    title: 'Churn Analysis',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 109_000),
    completed_at: isoOffset(BASE_TIME_MS, 135_000),
    elapsed_ms: 26_000,
    tokens_used: 8_900,
    cost_usd: 0.031,
  },
  {
    step_id: 'step-section-revenue',
    session_id: SEED_SESSION_ID,
    phase: 'section',
    title: 'Revenue Impact',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 136_000),
    completed_at: isoOffset(BASE_TIME_MS, 155_000),
    elapsed_ms: 19_000,
    tokens_used: 5_600,
    cost_usd: 0.019,
  },
  {
    step_id: 'step-section-recs',
    session_id: SEED_SESSION_ID,
    phase: 'section',
    title: 'Recommendations',
    status: 'done',
    started_at: isoOffset(BASE_TIME_MS, 156_000),
    completed_at: isoOffset(BASE_TIME_MS, 170_000),
    elapsed_ms: 14_000,
    tokens_used: 3_800,
    cost_usd: 0.013,
  },
];

const SEED_FIGURES: ResearchFigure[] = [
  {
    figure_id: 'fig-001',
    title: 'Survival Curve by Onboarding Cohort',
    caption:
      'Kaplan-Meier estimate of 30-day retention for users who completed vs. dropped at step 3.',
    image_path: '/echo/research/survival_curve.png',
    thumbnail_path: '/echo/research/survival_curve_thumb.png',
    source_step_id: 'step-code-1',
  },
  {
    figure_id: 'fig-002',
    title: 'Step-Level Funnel',
    caption: 'Conversion funnel across 5 onboarding steps (n=1,000).',
    image_path: '/echo/research/funnel.png',
    thumbnail_path: '/echo/research/funnel_thumb.png',
    source_step_id: 'step-execute',
  },
  {
    figure_id: 'fig-003',
    title: 'Revenue Impact Projection',
    caption: 'Projected monthly LTV recovery under three onboarding simplification scenarios.',
    image_path: '/echo/research/revenue_projection.png',
    thumbnail_path: '/echo/research/revenue_projection_thumb.png',
    source_step_id: 'step-section-revenue',
  },
];

const SEED_CLAIMS: ResearchClaim[] = [
  {
    claim_id: 'claim-001',
    text: 'Users who encounter >2 errors in step 3 churn at 2.3× the base rate.',
    evidence: [
      {
        evidence_id: 'ev-001',
        source: 'step-code-1',
        value: 'Hazard ratio = 2.31 (CI 1.8–2.9, p<0.001)',
        step_id: 'step-code-1',
        code_snippet: 'cph.fit(durations, event_observed, group="error_count")\nprint(cph.summary)',
      },
    ],
  },
  {
    claim_id: 'claim-002',
    text: '31.1% of users drop off at step 3 of onboarding.',
    evidence: [
      {
        evidence_id: 'ev-002',
        source: 'step-execute',
        value: '97 / 312 users = 31.1%',
        step_id: 'step-execute',
        code_snippet: 'df.query("step == 3 and status == \'drop\'").shape[0]',
      },
    ],
  },
  {
    claim_id: 'claim-003',
    text: 'A simplified onboarding flow recovers ~$18k/mo in projected LTV.',
    evidence: [
      {
        evidence_id: 'ev-003',
        source: 'step-section-revenue',
        value: '$18,200/mo (midpoint of $14k–$22k range)',
        step_id: 'step-section-revenue',
        code_snippet: 'ltv_model(reduction=0.10, cohort_size=1000)',
      },
    ],
  },
  {
    claim_id: 'claim-004',
    text: 'Replacing the free-text field with a dropdown will reduce step-3 time by 40%.',
    evidence: [
      {
        evidence_id: 'ev-004',
        source: 'step-observe',
        value: 'Median step-3 time with free-text: 94s; estimated with dropdown: 56s (−40.4%)',
        step_id: 'step-observe',
      },
    ],
  },
  {
    claim_id: 'claim-005',
    text: 'Support tickets (n=120) confirm step-3 errors as the top frustration.',
    evidence: [
      {
        evidence_id: 'ev-005',
        source: 'step-discover',
        value: '47/120 tickets (39.2%) mention step-3 errors',
        step_id: 'step-discover',
      },
    ],
  },
  {
    claim_id: 'claim-006',
    text: 'Price column has 3.2% missing values.',
    evidence: [
      {
        evidence_id: 'ev-006',
        source: 'step-analyze',
        value: '32 / 1000 rows missing in price',
        step_id: 'step-analyze',
        code_snippet: "df['price'].isna().mean()  # → 0.032",
      },
    ],
  },
];

const SEED_REPORT_MARKDOWN = `# Customer Churn & Onboarding Friction Analysis

## Executive Summary

This report analyses the causal relationship between onboarding friction and customer churn
using the 2024 sales dataset (n=1,000). Key finding: **users who encounter >2 errors in
step 3 churn at 2.3× the base rate**, and a simplified onboarding flow could recover
approximately **$18,200/month** in projected lifetime value.

## Data Overview

### Sources & Coverage

- **Primary**: Sales 2024 dataset (1,000 rows, 7 columns)
- **Secondary**: Support ticket corpus (n=120), workspace memory (4 prior analyses)

### Schema Summary

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

### Survival Curve

The Kaplan-Meier survival estimate reveals a sharp divergence at day 7:

\`\`\`python
from lifelines import KaplanMeierFitter
kmf = KaplanMeierFitter()
kmf.fit(durations, event_observed, group="error_count")
kmf.plot()
\`\`\`

Users with >2 step-3 errors show a hazard ratio of **2.31** (CI 1.8–2.9, p<0.001).

### Step-Level Funnel

312 users reached step 3; **97 dropped off (31.1%)**. The funnel shows step 3 as the
primary attrition point, with earlier steps converting at >85%.

### Error Correlation

A logistic regression confirms error count as the strongest predictor:

\`\`\`python
import statsmodels.api as sm
model = sm.Logit(churn, sm.add_constant(features)).fit()
# error_count: coef=0.84, p<0.001
\`\`\`

## Revenue Impact

### LTV Model

Using the observed churn rate and average revenue per user ($58/mo), the projected
monthly LTV loss from step-3 drop-off is:

- **Current**: $4,200/mo lost to step-3 churn
- **With 10% reduction**: $18,200/mo recovered

### Projection

Three scenarios modelled:

| Scenario | Step-3 Drop Reduction | Monthly LTV Recovery |
|----------|----------------------|---------------------|
| Conservative | 5% | $9,100 |
| **Moderate** | **10%** | **$18,200** |
| Aggressive | 20% | $36,400 |

## Recommendations

1. **Replace the free-text field in step 3 with a dropdown** — projected 40% time reduction.
2. **Add inline error recovery** — auto-suggest fixes for the top 3 validation errors.
3. **Implement a skip option** for returning users — reduces friction for power users.
4. **A/B test the simplified flow** — validate the 2.3× churn hypothesis with live traffic.

## Appendix

### Reproducibility

All analyses are reproducible from the Dream research workbench. The provenance file
(\`.provenance.json\`) links every claim to its source run.

### Raw Statistics

- Total rows analysed: 1,000
- Support tickets reviewed: 120
- Code runs executed: 4 (2 initial, 1 self-corrected, 1 final)
- Total tokens consumed: ~48,000
- Total cost: $0.18
`;

const SEED_SECTIONS: ResearchReportSection[] = [
  {
    section_id: 'sec-exec',
    title: 'Executive Summary',
    content:
      'This report analyses the causal relationship between onboarding friction and customer churn using the 2024 sales dataset (n=1,000). Key finding: users who encounter >2 errors in step 3 churn at 2.3× the base rate.',
  },
  {
    section_id: 'sec-data',
    title: 'Data Overview',
    content:
      'Primary: Sales 2024 dataset (1,000 rows, 7 columns). Secondary: Support ticket corpus (n=120).',
    children: [
      {
        section_id: 'sec-data-sources',
        title: 'Sources & Coverage',
        content: 'Primary: Sales 2024 dataset (1,000 rows, 7 columns)',
      },
      {
        section_id: 'sec-data-schema',
        title: 'Schema Summary',
        content: '7 columns: invoice_date, region, product, price, quantity, revenue, email',
      },
    ],
  },
  {
    section_id: 'sec-churn',
    title: 'Churn Analysis',
    content: 'Kaplan-Meier survival estimate reveals hazard ratio of 2.31 for high-error users.',
    children: [
      {
        section_id: 'sec-churn-survival',
        title: 'Survival Curve',
        content: 'KM estimate shows sharp divergence at day 7.',
      },
      {
        section_id: 'sec-churn-funnel',
        title: 'Step-Level Funnel',
        content: '312 users reached step 3; 97 dropped off (31.1%).',
      },
      {
        section_id: 'sec-churn-error',
        title: 'Error Correlation',
        content: 'Logistic regression: error_count coef=0.84, p<0.001.',
      },
    ],
  },
  {
    section_id: 'sec-revenue',
    title: 'Revenue Impact',
    content: 'Projected monthly LTV recovery under three scenarios: $9.1k, $18.2k, $36.4k.',
    children: [
      {
        section_id: 'sec-revenue-ltv',
        title: 'LTV Model',
        content: 'ARPU $58/mo, churn-adjusted LTV model.',
      },
      { section_id: 'sec-revenue-proj', title: 'Projection', content: 'Three scenarios modelled.' },
    ],
  },
  {
    section_id: 'sec-recs',
    title: 'Recommendations',
    content:
      'Replace free-text with dropdown, add inline error recovery, implement skip option, A/B test.',
  },
  {
    section_id: 'sec-appendix',
    title: 'Appendix',
    content: 'Reproducibility and raw statistics.',
    children: [
      {
        section_id: 'sec-appendix-repro',
        title: 'Reproducibility',
        content: 'All analyses reproducible from the Dream research workbench.',
      },
      {
        section_id: 'sec-appendix-stats',
        title: 'Raw Statistics',
        content: '1,000 rows, 120 tickets, 4 code runs, ~48k tokens, $0.18.',
      },
    ],
  },
];

const SEED_REPORT: ResearchReport = {
  session_id: SEED_SESSION_ID,
  title: 'Customer Churn & Onboarding Friction Analysis',
  markdown: SEED_REPORT_MARKDOWN,
  sections: SEED_SECTIONS,
  figures: SEED_FIGURES,
  claims: SEED_CLAIMS,
  generated_at: isoOffset(BASE_TIME_MS, 170_000),
};

// --------------------------------------------------------------------------- //
// In-memory session store
// --------------------------------------------------------------------------- //

const sessions = new Map<string, ResearchSession>();

function seedCompletedSession(): ResearchSession {
  const session: ResearchSession = {
    session_id: SEED_SESSION_ID,
    topic: 'Customer churn & onboarding friction',
    objective:
      'Analyse the causal relationship between onboarding step-3 errors and first-month churn.',
    status: 'completed',
    depth: 'deep',
    data_sources: [
      {
        source_id: 'ds-001',
        name: 'Sales 2024',
        kind: 'dataset',
        path: 'ec40da7a-...',
      },
    ],
    model_route: 'local (ollama/qwen2.5-coder:32b)',
    created_at: isoOffset(BASE_TIME_MS, 0),
    updated_at: isoOffset(BASE_TIME_MS, 170_000),
    started_at: isoOffset(BASE_TIME_MS, 1_000),
    completed_at: isoOffset(BASE_TIME_MS, 170_000),
    plan: SEED_PLAN,
    report: SEED_REPORT,
  };
  sessions.set(session.session_id, session);
  return session;
}

function seedFailedSession(): ResearchSession {
  const session: ResearchSession = {
    session_id: 'rsch-fail-001',
    topic: 'Quarterly revenue forecast',
    objective: 'Forecast Q3 2026 revenue from historical data.',
    status: 'failed',
    depth: 'simple',
    data_sources: [],
    model_route: 'local (ollama/llama3.1:8b)',
    created_at: isoOffset(BASE_TIME_MS, -86_400_000),
    updated_at: isoOffset(BASE_TIME_MS, -86_300_000),
    started_at: isoOffset(BASE_TIME_MS, -86_399_000),
    error: 'No data sources attached — cannot forecast without input data.',
  };
  sessions.set(session.session_id, session);
  return session;
}

// Pre-seed on module load so list() always returns data.
seedCompletedSession();
seedFailedSession();

// --------------------------------------------------------------------------- //
// Public API — mirrors the P1 contract method-for-method.
// --------------------------------------------------------------------------- //

/** List all research sessions (newest first). */
export function echoResearchList(): { sessions: ResearchSession[] } {
  return {
    sessions: [...sessions.values()].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    ),
  };
}

/** Get a single session by id. */
export function echoResearchGet(sessionId: string): ResearchSession {
  const session = sessions.get(sessionId);
  if (!session) throw new Error(`research session not found: ${sessionId}`);
  return session;
}

/** Create a new research session (status: pending). */
export function echoResearchCreate(params: ResearchCreateParams): ResearchSession {
  const random = makeRandom(Date.now());
  const sessionId = `rsch-${Math.floor(random() * 1e16)
    .toString(16)
    .padStart(16, '0')}`;
  const now = new Date().toISOString();
  const session: ResearchSession = {
    session_id: sessionId,
    topic: params.topic,
    objective: params.objective,
    status: 'pending',
    depth: params.depth,
    data_sources: params.data_sources,
    model_route: params.model_route ?? 'local (ollama/qwen2.5-coder:32b)',
    created_at: now,
    updated_at: now,
  };
  sessions.set(sessionId, session);
  return session;
}

/** Start a session — transitions to 'planning'. */
export function echoResearchStart(sessionId: string): ResearchSession {
  const session = echoResearchGet(sessionId);
  session.status = 'planning';
  session.started_at = new Date().toISOString();
  session.updated_at = session.started_at;
  return session;
}

/**
 * Simulate plan generation — returns the plan and moves the session to
 * 'awaiting_approval'.
 */
export function echoResearchPlan(sessionId: string): {
  session: ResearchSession;
  plan: ResearchPlan;
} {
  const session = echoResearchGet(sessionId);
  session.plan = { ...SEED_PLAN };
  session.status = 'awaiting_approval';
  session.updated_at = new Date().toISOString();
  return { session, plan: session.plan };
}

/** Approve a plan — moves the session to 'running'. */
export function echoResearchApprove(sessionId: string): ResearchSession {
  const session = echoResearchGet(sessionId);
  session.status = 'running';
  session.updated_at = new Date().toISOString();
  return session;
}

/** Modify a plan (human-in-the-loop edit). */
export function echoResearchModifyPlan(sessionId: string, plan: ResearchPlan): ResearchSession {
  const session = echoResearchGet(sessionId);
  session.plan = plan;
  session.updated_at = new Date().toISOString();
  return session;
}

/** Cancel a session. */
export function echoResearchStop(sessionId: string): ResearchSession {
  const session = echoResearchGet(sessionId);
  session.status = 'cancelled';
  session.updated_at = new Date().toISOString();
  session.completed_at = session.updated_at;
  return session;
}

/** Get the full report for a completed session. */
export function echoResearchReport(sessionId: string): ResearchReport {
  const session = echoResearchGet(sessionId);
  if (!session.report) throw new Error(`no report for session ${sessionId}`);
  return session.report;
}

/** Get the execution trace (all steps) for a session. */
export function echoResearchTrace(sessionId: string): { steps: ResearchStep[] } {
  echoResearchGet(sessionId); // validate existence
  return { steps: SEED_STEPS };
}

/** Estimate cost before starting. */
export function echoResearchEstimate(params: ResearchCreateParams): ResearchCostEstimate {
  const base = params.depth === 'deep' ? 185_000 : 45_000;
  const costPer1k = 0.0023;
  return {
    estimated_tokens: base,
    estimated_cost_usd: Math.round((base / 1000) * costPer1k * 100) / 100,
    estimated_duration_seconds: params.depth === 'deep' ? 300 : 90,
    breaks_down: [
      { phase: 'analyze', tokens: Math.round(base * 0.06), cost_usd: 0.02 },
      { phase: 'plan', tokens: Math.round(base * 0.08), cost_usd: 0.03 },
      { phase: 'discover', tokens: Math.round(base * 0.15), cost_usd: 0.05 },
      { phase: 'code', tokens: Math.round(base * 0.25), cost_usd: 0.09 },
      { phase: 'execute', tokens: Math.round(base * 0.12), cost_usd: 0.04 },
      { phase: 'observe', tokens: Math.round(base * 0.14), cost_usd: 0.05 },
      { phase: 'evidence', tokens: Math.round(base * 0.05), cost_usd: 0.02 },
      { phase: 'section', tokens: Math.round(base * 0.15), cost_usd: 0.12 },
    ],
  };
}

/**
 * Generate a streaming progress simulation.
 *
 * Yields `ResearchProgressEvent` objects via the callback at deterministic
 * intervals, simulating the live trace. Honors the `signal` for cancellation.
 */
export function echoResearchStreamProgress(
  sessionId: string,
  onEvent: (event: ResearchProgressEvent) => void,
  signal?: AbortSignal,
): Promise<ResearchSession> {
  echoResearchGet(sessionId); // validate
  return new Promise((resolve, reject) => {
    let stepIndex = 0;
    const interval = setInterval(() => {
      if (signal?.aborted) {
        clearInterval(interval);
        reject(new Error('cancelled'));
        return;
      }

      // Emit heartbeat every tick
      onEvent({
        session_id: sessionId,
        event_type: 'heartbeat',
        timestamp: new Date().toISOString(),
      });

      if (stepIndex < SEED_STEPS.length) {
        const step = SEED_STEPS[stepIndex];
        // Step started
        onEvent({
          session_id: sessionId,
          event_type: 'step_started',
          step: { ...step, status: 'running' },
          timestamp: step.started_at ?? new Date().toISOString(),
        });

        // Step output (if any)
        if (step.output) {
          onEvent({
            session_id: sessionId,
            event_type: 'output',
            output: step.output,
            timestamp: step.started_at ?? new Date().toISOString(),
          });
        }

        // Tool calls (if any)
        if (step.tool_calls) {
          for (const tc of step.tool_calls) {
            onEvent({
              session_id: sessionId,
              event_type: 'tool_call',
              tool_call: tc,
              timestamp: tc.started_at,
            });
          }
        }

        // Step completed (or failed — simulate the self-corrected error)
        const hasError = step.tool_calls?.some((tc) => tc.error);
        if (hasError) {
          // Emit a brief 'step_failed' then immediately recover
          onEvent({
            session_id: sessionId,
            event_type: 'step_failed',
            step: { ...step, status: 'blocked', error: 'Self-correcting…' },
            timestamp: step.completed_at ?? new Date().toISOString(),
          });
        }
        onEvent({
          session_id: sessionId,
          event_type: 'step_completed',
          step: { ...step, status: 'done' },
          timestamp: step.completed_at ?? new Date().toISOString(),
        });

        stepIndex += 1;
      } else {
        clearInterval(interval);
        // Mark session completed
        const session = echoResearchGet(sessionId);
        session.status = 'completed';
        session.completed_at = new Date().toISOString();
        session.updated_at = session.completed_at;
        session.report = SEED_REPORT;
        resolve(session);
      }
    }, 200); // fast interval for demo — 200ms per step

    // Cleanup on abort
    signal?.addEventListener(
      'abort',
      () => {
        clearInterval(interval);
        reject(new Error('cancelled'));
      },
      { once: true },
    );
  });
}

/** Get the seed session id (for tests). */
export function getSeedSessionId(): string {
  return SEED_SESSION_ID;
}

/** Reset sessions to seed state (for tests). */
export function resetEchoResearch(): void {
  sessions.clear();
  seedCompletedSession();
  seedFailedSession();
}
