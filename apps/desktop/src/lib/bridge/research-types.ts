/**
 * Type definitions for the `research.*` RPC family (P2).
 *
 * Mirrors the P1 wire format exactly:
 *   - `dream/research/schemas.py` (SessionRecord, Plan, Section, etc.)
 *   - `dream/bridge/methods_research.py` (handler params + return shapes)
 *
 * UI-only view-models (step cards, trace filters) live in the store, not here.
 */

// --------------------------------------------------------------------------- //
// P1 statuses (schemas.STATUSES)
// --------------------------------------------------------------------------- //

export type ResearchStatus =
  | 'IDLE'
  | 'PLANNING'
  | 'APPROVAL_PENDING'
  | 'IN_PROGRESS'
  | 'PROOFREAD'
  | 'COMPILING'
  | 'COMPLETE'
  | 'FAILED'
  | 'CANCELLED';

export type SectionStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'SKIPPED' | 'FAILED';

export type OutputLength = 'brief' | 'standard' | 'detailed';

// --------------------------------------------------------------------------- //
// P1 config (schemas.ResearchConfig)
// --------------------------------------------------------------------------- //

export interface ResearchConfig {
  max_iterations: number;
  max_time_seconds: number;
  step_timeout_seconds: number;
  max_retries: number;
  max_sections: number;
  language: string;
  autonomous: boolean;
  allow_network: boolean;
  max_pages: number;
  output_length: OutputLength;
}

// --------------------------------------------------------------------------- //
// P1 plan + sections (schemas.Plan, Section, Iteration, Finding, etc.)
// --------------------------------------------------------------------------- //

export interface ToolCallRecord {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error: string;
  summary: string;
  elapsed_seconds: number;
}

export interface Observation {
  stdout: string;
  stderr: string;
  result: Record<string, unknown>;
  facts: string[];
  error: string;
  converged: boolean;
}

export interface Iteration {
  index: number;
  knowledge_gap: string;
  tool_calls: ToolCallRecord[];
  code: string;
  observation: Observation;
  reflection: string;
  retries: number;
  started_at: number;
  elapsed_seconds: number;
}

export interface Finding {
  claim: string;
  evidence: string;
  metric: string;
  value: unknown;
  kind: string; // observation | anomaly | root_cause | recommendation
  section_id: string;
  iteration: number;
  grounded: boolean;
}

export interface Section {
  section_id: string;
  title: string;
  thesis: string;
  questions: string[];
  status: SectionStatus;
  iterations: Iteration[];
  findings: Finding[];
  charts: string[];
  tables: Record<string, unknown>[];
  prose: string;
  rationale: string;
  editable: boolean;
}

export interface Plan {
  objective: string;
  questions: string[];
  hypotheses: string[];
  methodology: string;
  sections: Section[];
  datasets: string[];
  revision: number;
  approved: boolean;
  source: string; // model | fallback | user
}

// --------------------------------------------------------------------------- //
// P1 report (schemas.ReportRef)
// --------------------------------------------------------------------------- //

export interface ReportRef {
  markdown_path: string;
  pdf_path: string;
  bundle_path: string;
  record_ids: string[];
  pages: number;
  proofread: Record<string, unknown>;
}

// --------------------------------------------------------------------------- //
// P1 cost estimate (ResearchSession.estimate_cost)
// --------------------------------------------------------------------------- //

export interface CostEstimate {
  sections: number;
  max_iterations: number;
  estimated_model_calls: number;
  estimated_tokens: number;
  estimated_sandbox_runs: number;
  max_wall_clock_seconds: number;
  backend: string;
}

// --------------------------------------------------------------------------- //
// P1 events (ResearchSession.emit shape)
// --------------------------------------------------------------------------- //

/** A progress event recorded by the session. */
export interface ResearchEvent {
  event: string;
  ts: number;
  [key: string]: unknown;
}

// --------------------------------------------------------------------------- //
// P1 session record (schemas.SessionRecord.to_dict)
// --------------------------------------------------------------------------- //

export interface SessionRecord {
  session_id: string;
  topic: string;
  workspace: string;
  status: ResearchStatus;
  config: ResearchConfig;
  plan: Plan;
  sources: Record<string, unknown>[];
  report: ReportRef;
  events: ResearchEvent[];
  error: string;
  created_at: number;
  updated_at: number;
  cost_estimate: CostEstimate;
  published: boolean;
}

// --------------------------------------------------------------------------- //
// P1 summary (_summary in methods_research.py)
// --------------------------------------------------------------------------- //

export interface SessionSummary {
  session_id: string;
  status: ResearchStatus;
  topic: string;
  sections_total: number;
  sections_done: number;
  progress: number;
  events: number;
  error: string;
  published: boolean;
  report: ReportRef;
  cost_estimate: CostEstimate;
}

// --------------------------------------------------------------------------- //
// P1 list summary (ResearchEngine.list)
// --------------------------------------------------------------------------- //

export interface ListSummary {
  session_id: string;
  topic: string;
  status: ResearchStatus;
  sections: number;
  created_at: number;
  updated_at: number;
  published: boolean;
  report: string; // markdown_path
}

// --------------------------------------------------------------------------- //
// RPC params
// --------------------------------------------------------------------------- //

/** `research.create` params. */
export interface ResearchCreateParams {
  topic: string;
  workspace: string;
  config?: Partial<ResearchConfig>;
}

/** `research.modify` params. */
export interface ResearchModifyParams {
  session_id: string;
  changes: Record<string, unknown>;
}

/** `research.status` params. */
export interface ResearchStatusParams {
  session_id: string;
  cursor?: number;
}

/** `research.stream` params. */
export interface ResearchStreamParams {
  session_id: string;
  cursor?: number;
  timeout?: number;
  follow?: boolean;
}

// --------------------------------------------------------------------------- //
// RPC return shapes
// --------------------------------------------------------------------------- //

/** `research.list` return. */
export interface ResearchListResult {
  sessions: ListSummary[];
  count: number;
}

/** `research.plan` / `research.approve` / `research.modify` return. */
export interface PlanResult extends SessionSummary {
  plan: Plan;
}

/** `research.status` return. */
export interface StatusResult extends SessionSummary {
  cursor: number;
  new_events: ResearchEvent[];
}

/** `research.stream` chunk shape. */
export interface StreamChunk {
  event: ResearchEvent;
  cursor: number;
}

/** `research.export` return. */
export interface ExportResult extends SessionSummary {
  report: ReportRef;
}
