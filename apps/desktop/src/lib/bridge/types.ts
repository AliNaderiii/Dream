/**
 * JSON-RPC 2.0 type definitions for the Dream bridge.
 *
 * Mirrors the wire protocol in `docs/bridge/protocol.md`. These are the types
 * the frontend speaks; the Rust command surface (`bridge_send`) and the Python
 * sidecar agree on the same shapes.
 */

/** Any valid JSON-RPC 2.0 id (number or string). */
export type RpcId = number | string;

/** Parameters object for every method — always an object, never an array. */
export type RpcParams = Record<string, unknown>;

/** The standard JSON-RPC 2.0 envelope. */
export interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: RpcId;
  method: string;
  params?: RpcParams;
}

/** A successful JSON-RPC response. */
export interface JsonRpcResult<T = unknown> {
  jsonrpc: '2.0';
  id: RpcId;
  result: T;
}

/** A JSON-RPC error object. */
export interface RpcErrorObject {
  code: number;
  message: string;
  data?: Record<string, unknown>;
}

/** A failed JSON-RPC response. */
export interface JsonRpcError {
  jsonrpc: '2.0';
  id: RpcId | null;
  error: RpcErrorObject;
}

/** A server notification (no id). */
export interface JsonRpcNotification<T = unknown> {
  jsonrpc: '2.0';
  method: string;
  params: T;
}

// --------------------------------------------------------------------------- //
// Error taxonomy — kept in lock-step with `dream/bridge/errors.py`.
// --------------------------------------------------------------------------- //

export const RPC_ERROR = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603,
  PROVIDER_ERROR: -32001,
  AUTH_ERROR: -32002,
  RATE_LIMITED: -32003,
  CONTEXT_OVERFLOW: -32004,
  APPROVAL_REQUIRED: -32005,
  TOOL_ERROR: -32006,
  RESOURCE_EXHAUSTED: -32007,
} as const;

export type RpcErrorCode = (typeof RPC_ERROR)[keyof typeof RPC_ERROR];

/** Human-readable label for an error code, for the status indicator. */
export const RPC_ERROR_LABEL: Record<number, string> = {
  [RPC_ERROR.PARSE_ERROR]: 'Malformed message',
  [RPC_ERROR.INVALID_REQUEST]: 'Invalid request',
  [RPC_ERROR.METHOD_NOT_FOUND]: 'Unknown method',
  [RPC_ERROR.INVALID_PARAMS]: 'Invalid parameters',
  [RPC_ERROR.INTERNAL_ERROR]: 'Internal error',
  [RPC_ERROR.PROVIDER_ERROR]: 'Provider error',
  [RPC_ERROR.AUTH_ERROR]: 'Authentication failed',
  [RPC_ERROR.RATE_LIMITED]: 'Rate limited',
  [RPC_ERROR.CONTEXT_OVERFLOW]: 'Context overflow',
  [RPC_ERROR.APPROVAL_REQUIRED]: 'Approval required',
  [RPC_ERROR.TOOL_ERROR]: 'Tool error',
  [RPC_ERROR.RESOURCE_EXHAUSTED]: 'Too many requests',
};

// --------------------------------------------------------------------------- //
// Method result shapes — a typed subset the UI relies on.
// --------------------------------------------------------------------------- //

/** A durable memory row. Mirrors `Memory` in the protocol. */
export interface BridgeMemory {
  id: number;
  kind: string;
  content: string;
  tags: string[];
  importance: number;
  created_at: number;
  last_used_at: number;
  use_count: number;
  source: string;
  archived: boolean;
  pinned: boolean;
  score: number;
}

/** One conversation session. */
export interface BridgeSession {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  provider: string;
}

/** One step in a tool call recorded on a turn. */
export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  allowed: boolean;
  result: string;
}

/** The outcome of one agent turn. Mirrors `Turn` in the protocol. */
export interface BridgeTurn {
  reply: string;
  tool_calls: ToolCall[];
  memories_used: BridgeMemory[];
  memories_injected_ids: number[];
  memories_created: BridgeMemory[];
  memories_superseded: BridgeMemory[];
  memories_merged: BridgeMemory[];
  elapsed_seconds: number;
  extraction: { status: string; facts: unknown[]; raw_text: string };
  memory_errors: string[];
  /** Present when the turn was stopped before producing a reply. */
  stopped?: boolean;
}

/** A registered tool. */
export interface BridgeTool {
  name: string;
  risk: 'safe' | 'guarded' | 'dangerous';
  description: string;
  schema: Record<string, unknown>;
}

/** The three memory kinds Dream stores. Mirrors `dream.memory.KINDS`. */
export const MEMORY_KINDS = ['semantic', 'episodic', 'procedural'] as const;
export type MemoryKind = (typeof MEMORY_KINDS)[number];

/** Sort orders accepted by `memory.list`. */
export const MEMORY_SORTS = ['relevance', 'date_newest', 'date_oldest', 'importance'] as const;
export type MemorySort = (typeof MEMORY_SORTS)[number];

/** Filter/paging arguments for `memory.list`. */
export interface MemoryListParams {
  cursor?: string | null;
  limit?: number;
  kind_filter?: MemoryKind | MemoryKind[] | null;
  search_query?: string | null;
  /** Unix seconds, inclusive lower bound on `created_at`. */
  date_from?: number | null;
  /** Unix seconds, inclusive upper bound on `created_at`. */
  date_to?: number | null;
  /** Backend scale, 0.0–1.0. */
  min_importance?: number | null;
  sort_by?: MemorySort;
  include_archived?: boolean;
}

/** One page of memories plus cursor metadata. */
export interface MemoryListResult {
  memories: BridgeMemory[];
  total: number;
  next_cursor: string | null;
  has_more: boolean;
}

/** Per-kind totals used by the filter-tab badges. */
export interface MemoryCountResult {
  total: number;
  by_kind: Record<string, number>;
  archived: number;
}

/** Result of `memory.create` / `memory.update`. */
export interface MemoryMutationResult {
  memory: BridgeMemory;
}

/** Result of `memory.delete`. */
export interface MemoryDeleteResult {
  deleted: boolean;
  memory_id: number;
}

/** Result of `memory.search`. */
export interface MemorySearchResult {
  memories: BridgeMemory[];
}

/** A skill. */
export interface BridgeSkill {
  name: string;
  description: string;
  steps: string[];
  filename: string;
}

/** A skill row from `skill.list`, carrying the bridge-side enabled flag. */
export interface BridgeSkillEx extends BridgeSkill {
  enabled: boolean;
}

/** Full skill detail from `skill.get`, including the rendered file text. */
export interface BridgeSkillDetail extends BridgeSkillEx {
  /** Unix seconds from the file's mtime; 0 when unknown. */
  created_at: number;
  content: string;
}

/** A skill file that failed to parse. */
export interface BridgeSkillProblem {
  filename: string;
  detail: string;
}

/** Result of `skill.list`. */
export interface SkillListResult {
  skills: BridgeSkillEx[];
  problems: BridgeSkillProblem[];
}

/** Result of `skill.get`. */
export interface SkillGetResult {
  match: BridgeSkillDetail | null;
}

/** Result of `skill.install` — `conflict` when a same-named skill exists. */
export interface SkillInstallResult {
  filename: string;
  status: 'installed' | 'conflict';
  name: string;
  conflict?: boolean;
  existing_filename?: string;
}

/** Result of `skill.delete`. */
export interface SkillDeleteResult {
  deleted: boolean;
  filename: string;
  name: string;
}

/** Result of `skill.enable` / `skill.disable`. */
export interface SkillToggleResult {
  name: string;
  filename: string;
  enabled: boolean;
}

/** Result of `skill.export`. */
export interface SkillExportResult {
  name: string;
  filename: string;
  content: string;
}

// --------------------------------------------------------------------------- //
// Subagents — mirrors `subagent_to_dict` in `dream/subagents.py`.
// --------------------------------------------------------------------------- //

/** Lifecycle states a subagent can be in. Mirrors `SUBAGENT_STATUSES`. */
export const SUBAGENT_STATUSES = [
  'idle',
  'running',
  'paused',
  'completed',
  'failed',
  'cancelled',
  'timeout',
] as const;

export type SubAgentStatus = (typeof SUBAGENT_STATUSES)[number];

/** States from which a subagent will never move again. */
export const TERMINAL_SUBAGENT_STATUSES: readonly SubAgentStatus[] = [
  'completed',
  'failed',
  'cancelled',
  'timeout',
];

/** Whether a subagent has finished for good. */
export function isTerminalStatus(status: SubAgentStatus): boolean {
  return TERMINAL_SUBAGENT_STATUSES.includes(status);
}

/** One line of a subagent's activity log. */
export interface BridgeLogEntry {
  ts: number;
  level: string;
  message: string;
}

/** A spawned subagent and its live counters. */
export interface BridgeSubagent {
  subagent_id: string;
  id: string;
  name: string;
  parent_session_id: string | null;
  model_provider: string;
  model_name: string;
  system_prompt: string;
  tools: string[];
  prompt: string;
  context: string;
  status: SubAgentStatus;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  max_turns: number;
  max_tokens: number;
  max_duration: number;
  turn_count: number;
  token_count: number;
  result: string | null;
  error: string | null;
  pipeline_id: string | null;
  pipeline_index: number | null;
  /** Which limit ended the run — `turns`, `tokens` or `duration`. */
  limit_hit: string | null;
  elapsed: number;
  /** 0–1, the highest of the turn, token and time ratios. */
  progress: number;
  /** Omitted by `subagent.list`, which returns rows without their logs. */
  log?: BridgeLogEntry[];
}

/** `subagent.spawn` parameters. Limits fall back to the sidecar defaults. */
export interface SpawnSubagentParams extends RpcParams {
  prompt: string;
  name?: string;
  context?: string;
  system_prompt?: string;
  model_provider?: string;
  model_name?: string;
  tools?: string[];
  max_turns?: number;
  max_tokens?: number;
  max_duration?: number;
  parent_session_id?: string | null;
}

// --------------------------------------------------------------------------- //
// Schedules — mirrors `schedule_to_dict` / `run_to_dict` in `dream/scheduler.py`.
// --------------------------------------------------------------------------- //

/** Outcome of one scheduled execution. Mirrors `RUN_STATUSES`. */
export type ScheduleRunStatus = 'running' | 'success' | 'error' | 'approval_denied';

/** A recurring prompt and its next fire time. */
export interface BridgeSchedule {
  schedule_id: string;
  id: string;
  name: string;
  description: string;
  cron_expression: string;
  /** The phrase the user typed, kept so the form can round-trip it. */
  natural_language: string | null;
  /** Server-rendered reading of the cron expression. */
  human: string;
  prompt: string;
  session_id: string | null;
  enabled: boolean;
  last_run: number | null;
  next_run: number | null;
  created_at: number;
  max_runs: number | null;
  run_count: number;
  require_approval: boolean;
  /** True once `run_count` has reached `max_runs`. */
  exhausted: boolean;
  /** Only `schedule.get` includes recent history. */
  runs?: BridgeScheduleRun[];
}

/** One row of a schedule's execution history. */
export interface BridgeScheduleRun {
  id: number;
  schedule_id: string;
  started_at: number;
  completed_at: number | null;
  duration: number | null;
  result_summary: string;
  status: ScheduleRunStatus;
}

/** `schedule.preview` result — never throws, reports invalid input inline. */
export interface SchedulePreview {
  valid: boolean;
  cron_expression: string | null;
  human: string | null;
  next_run: number | null;
  natural_language: string | null;
  error: string | null;
}

// --------------------------------------------------------------------------- //
// Connectivity gateway — mirrors `gateway.*` in `dream/connectivity/gateway.py`.
// --------------------------------------------------------------------------- //

/** The six platforms the gateway serves, in catalog order. */
export const GATEWAY_PLATFORM_NAMES = [
  'telegram',
  'discord',
  'slack',
  'whatsapp',
  'signal',
  'email',
] as const;

export type GatewayPlatformName = (typeof GATEWAY_PLATFORM_NAMES)[number];

/** Content privacy of one platform: `e2e` content is never logged. */
export type GatewayPrivacy = 'plaintext' | 'e2e';

/** One config field of a platform (drives the configure form). */
export interface GatewayPlatformField {
  key: string;
  label: string;
  type: 'text' | 'secret' | 'number' | 'boolean';
  secret?: boolean;
  required?: boolean;
  placeholder?: string;
  default?: string | number | boolean;
}

/** A platform's static capabilities plus its public (redacted) config. */
export interface GatewayPlatform {
  name: GatewayPlatformName;
  label: string;
  description: string;
  privacy: GatewayPrivacy;
  max_message_length: number;
  supports_inline: boolean;
  supports_attachments: boolean;
  fields: GatewayPlatformField[];
  enabled: boolean;
  configured: boolean;
}

/** One adapter's observable state inside `gateway.status`. */
export interface GatewayAdapterStatus {
  platform: string;
  running: boolean;
  connected: boolean;
  last_activity: string | null;
  error: string | null;
  detail: string;
}

/** A chat identity authorised to talk to the agent on one platform. */
export interface GatewayLinkedUser {
  platform: string;
  user_id: string;
  display_name: string;
  linked_at: number;
}

/** `gateway.status` result. */
export interface GatewayStatusResult {
  running: boolean;
  started_at: number | null;
  adapters: GatewayAdapterStatus[];
  linked_users: GatewayLinkedUser[];
  messages: { inbound: number; outbound: number };
  rate_limit: {
    limits: Record<string, number>;
    default: number;
    active: Record<string, Record<string, number>>;
  };
}

/** One message-log row (`gateway.logs`). `text` is empty for e2e platforms. */
export interface GatewayLogEntry {
  platform: string;
  direction: 'in' | 'out';
  user_id: string;
  text: string;
  timestamp: string;
  message_id: string | null;
  attachments: number;
}

/** `gateway.logs` result. */
export interface GatewayLogsResult {
  platform: string | null;
  entries: GatewayLogEntry[];
  total: number;
}

/** `gateway.link_code` result. */
export interface GatewayLinkCodeResult {
  platform: string;
  code: string;
  issued_at: number;
  expires_at: number;
  user_id: string | null;
}

/** `gateway.configure` result — `config` is always redacted. */
export interface GatewayConfigureResult {
  saved: boolean;
  platform: string;
  config: Record<string, unknown>;
}

/** Redacted public config for one platform (secrets are masked). */
export interface GatewayPlatformConfig {
  [key: string]: unknown;
  enabled: boolean;
  configured: boolean;
  secret_fields: string[];
}

/** Connection lifecycle of the bridge, surfaced in the status bar. */
export type BridgeConnectionState = 'connecting' | 'ready' | 'reconnecting' | 'disconnected';

/** A stream chunk routed from a `stream.chunk` notification. */
export interface StreamChunk {
  id: RpcId;
  token: string;
  /** Reserved for future non-text chunk kinds (tool calls, etc.). */
  event?: string;
  /** Subagent that produced this chunk, on `subagent.logs` streams. */
  subagent_id?: string;
  /** Structured log line, on `subagent.logs` streams. */
  entry?: BridgeLogEntry;
}

// ---------------------------------------------------------------------------
// P-08: Docker sandbox types
// ---------------------------------------------------------------------------

/** Resource limits for a sandbox execution. */
export interface SandboxResourceLimits {
  cpu_count: number;
  memory_mb: number;
  disk_mb: number;
  network_enabled: boolean;
  timeout_seconds: number;
  pids_limit: number;
}

/** Result of a sandbox code execution. */
export interface SandboxResult {
  stdout: string;
  stderr: string;
  return_code: number;
  timed_out: boolean;
  output_files: string[];
  elapsed_seconds: number;
  error: string | null;
}

/** Sandbox status (Docker availability, images, etc.). */
export interface SandboxStatus {
  available: boolean;
  docker: Record<string, unknown> | false;
  images_available: Record<string, boolean> | undefined;
  default_images: Record<string, string> | undefined;
  keep_containers: boolean;
  data_dir: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// P-08: Browser control types
// ---------------------------------------------------------------------------

/** Browser page content. */
export interface BrowserPageContent {
  url: string;
  title: string;
  text: string;
  links: Array<{ text: string; href: string }>;
  tables: string[][][];
  screenshot_path?: string;
}

/** Browser session approval state. */
export interface BrowserSession {
  session_id: string;
  url: string;
  purpose: string;
  domain: string;
  status: 'pending' | 'active' | 'closed';
}

/** Browser controller status. */
export interface BrowserStatus {
  attached: boolean;
  attached_to_existing: boolean;
  has_page: boolean;
  pending_approvals: number;
  approved_domains: string[];
  current_session: BrowserSession | null;
  screenshot_dir: string;
}

// ---------------------------------------------------------------------------
// P-08: Web gateway types
// ---------------------------------------------------------------------------

/** Gateway token info (display-safe, partial token). */
export interface GatewayTokenInfo {
  prefix: string;
  scope: 'read' | 'write';
  label: string;
  created_at: number;
  last_used_at: number | null;
}

/** Gateway token with full value (for settings display). */
export interface GatewayTokenFull {
  scope: 'read' | 'write';
  label: string;
  created_at: number;
  last_used_at: number | null;
}

/** Gateway status. */
export interface GatewayStatus {
  enabled: boolean;
  token_count: number;
  tokens: GatewayTokenInfo[];
  has_setup_token: boolean;
}

/** Active gateway connection. */
export interface GatewayConnection {
  id: string;
  ip: string;
  device: string;
  scope: string;
  user_agent: string;
  connected_at: number;
}
