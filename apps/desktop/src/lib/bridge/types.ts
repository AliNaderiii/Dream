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

/** Connection lifecycle of the bridge, surfaced in the status bar. */
export type BridgeConnectionState = 'connecting' | 'ready' | 'reconnecting' | 'disconnected';

/** A stream chunk routed from a `stream.chunk` notification. */
export interface StreamChunk {
  id: RpcId;
  token: string;
  /** Reserved for future non-text chunk kinds (tool calls, etc.). */
  event?: string;
}
