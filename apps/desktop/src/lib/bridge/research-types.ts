/**
 * Type definitions for the `research.*` RPC family (P2).
 *
 * Mirrors the P1 contract from `dream/bridge/methods.py` so the frontend
 * speaks the same wire shapes. These are kept in a dedicated module so
 * `research.ts` and `echo-research.ts` share one source of truth.
 */

/** Research depth controls iteration budget and output length. */
export type ResearchDepth = 'simple' | 'deep';

/** Status of a research session. */
export type ResearchStatus =
  'pending' | 'planning' | 'awaiting_approval' | 'running' | 'completed' | 'failed' | 'cancelled';

/** Status of an individual step within a session. */
export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'blocked';

/** Labeled phase for a step (mirrors the P1 execution trace). */
export type StepPhase =
  'analyze' | 'plan' | 'discover' | 'code' | 'execute' | 'observe' | 'evidence' | 'section';

/** Risk tier for tool calls (surfaced in the trace inspector). */
export type RiskTier = 'safe' | 'caution' | 'danger';

/** A data source attached to a research session. */
export interface ResearchDataSource {
  source_id: string;
  name: string;
  kind: 'dataset' | 'file' | 'url';
  path?: string;
}

/** Parameters for `research.create`. */
export interface ResearchCreateParams {
  topic: string;
  objective: string;
  depth: ResearchDepth;
  data_sources: ResearchDataSource[];
  model_route?: string;
  max_iterations?: number;
  max_time_seconds?: number;
}

/** A research plan returned by the planner. */
export interface ResearchPlan {
  research_questions: string[];
  hypotheses: string[];
  methodology: string;
  outline: ResearchOutlineNode[];
  estimated_cost_usd?: number;
  estimated_tokens?: number;
}

/** A node in the report outline tree. */
export interface ResearchOutlineNode {
  title: string;
  children?: ResearchOutlineNode[];
}

/** A research session summary. */
export interface ResearchSession {
  session_id: string;
  topic: string;
  objective: string;
  status: ResearchStatus;
  depth: ResearchDepth;
  data_sources: ResearchDataSource[];
  model_route: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  plan?: ResearchPlan;
  report?: ResearchReport;
  error?: string;
}

/** A step in the execution trace. */
export interface ResearchStep {
  step_id: string;
  session_id: string;
  phase: StepPhase;
  title: string;
  status: StepStatus;
  started_at?: string;
  completed_at?: string;
  elapsed_ms?: number;
  tokens_used?: number;
  cost_usd?: number;
  output?: string;
  error?: string;
  tool_calls?: ResearchToolCall[];
}

/** A tool call within a step. */
export interface ResearchToolCall {
  call_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  result?: string;
  error?: string;
  risk_tier: RiskTier;
  started_at: string;
  completed_at?: string;
}

/** A completed research report. */
export interface ResearchReport {
  session_id: string;
  title: string;
  markdown: string;
  sections: ResearchReportSection[];
  figures: ResearchFigure[];
  claims: ResearchClaim[];
  generated_at: string;
}

/** A section within a report. */
export interface ResearchReportSection {
  section_id: string;
  title: string;
  content: string;
  children?: ResearchReportSection[];
}

/** A figure (chart/plot) in the report. */
export interface ResearchFigure {
  figure_id: string;
  title: string;
  caption: string;
  image_path: string;
  thumbnail_path?: string;
  source_step_id?: string;
}

/** A claim linked to its evidence (for the integrity view). */
export interface ResearchClaim {
  claim_id: string;
  text: string;
  evidence: ResearchEvidence[];
}

/** Evidence supporting a claim. */
export interface ResearchEvidence {
  evidence_id: string;
  source: string;
  value: string;
  step_id?: string;
  code_snippet?: string;
}

/** Parameters for `research.modify_plan`. */
export interface ResearchModifyPlanParams {
  session_id: string;
  plan: ResearchPlan;
}

/** Streaming event from `research.stream_progress`. */
export interface ResearchProgressEvent {
  session_id: string;
  event_type:
    'step_started' | 'step_completed' | 'step_failed' | 'output' | 'tool_call' | 'heartbeat';
  step?: ResearchStep;
  output?: string;
  tool_call?: ResearchToolCall;
  timestamp: string;
}

/** Cost estimate returned by `research.estimate_cost`. */
export interface ResearchCostEstimate {
  estimated_tokens: number;
  estimated_cost_usd: number;
  estimated_duration_seconds: number;
  breaks_down: {
    phase: StepPhase;
    tokens: number;
    cost_usd: number;
  }[];
}
