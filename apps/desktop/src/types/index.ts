/** Shared type definitions for the Dream desktop shell. */

/** Lifecycle of the Dream agent. Mirrors `state::AgentStatus` in Rust. */
export type AgentStatus = 'idle' | 'running' | 'paused' | 'error' | 'offline';

/** UI colour theme. `system` follows the OS preference. */
export type ThemeMode = 'light' | 'dark' | 'system';

/** Resolved theme actually applied to the DOM (never `system`). */
export type ResolvedTheme = 'light' | 'dark';

/** Writing direction. Persian/Arabic render right-to-left. */
export type Direction = 'ltr' | 'rtl';

/** UI language. */
export type Locale = 'en' | 'fa';

/** Layout density. Compact multiplies component padding by 0.75. */
export type Density = 'comfortable' | 'compact';

/** Snapshot of Rust-side app state. Mirrors `state::AppStateSnapshot`. */
export interface AppStateSnapshot {
  agentStatus: AgentStatus;
  pendingApprovals: number;
  workspaceRoot: string | null;
  minimizeToTray: boolean;
  closeToTray: boolean;
}

/** A validated filesystem entry returned by the dialog commands. */
export interface FileEntry {
  path: string;
  name: string;
  extension: string | null;
  size: number;
  isDir: boolean;
}

/** Outcome of a notification send attempt. Mirrors `SendOutcome` in Rust. */
export type SendOutcome = 'shown' | 'duplicate' | 'denied';

/** Notification permission state. */
export type NotificationPermission = 'granted' | 'denied' | 'prompt';

/** Payload accepted by the `send_notification` command. */
export interface NotificationRequest {
  title: string;
  body: string;
  id?: string;
  group?: string;
  ongoing?: boolean;
}

/** Risk tier of a tool call, per the design system's risk trio. */
export type RiskTier = 'safe' | 'guarded' | 'dangerous';

/** A rendered tool invocation attached to an assistant turn. */
export interface MessageToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  status: 'running' | 'ok' | 'error' | 'blocked';
  risk: RiskTier;
}

/** A single transcript row. */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool' | 'error';
  content: string;
  createdAt: number;
  status?: 'streaming' | 'complete' | 'error';
  toolCalls?: MessageToolCall[];
  attachments?: { name: string; path?: string; url?: string; type?: string }[];
  errorCode?: number;
}

/** A conversation session. */
export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  modelProvider?: string;
  modelName?: string;
  isArchived?: boolean;
  projectId?: string;
}

/** Kind of model provider Dream can talk to. */
export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'openai-compatible' | 'echo';

/** Connection state of a provider, shown in the status bar and provider list. */
export type ProviderStatus = 'connected' | 'disconnected' | 'testing' | 'error';

/** A single model exposed by a provider. */
export interface Model {
  id: string;
  name: string;
  providerId: string;
  contextWindow?: number;
}

/** A configured model provider. */
export interface Provider {
  id: string;
  name: string;
  kind: ProviderKind;
  status: ProviderStatus;
  /** True when the provider runs on this machine (no network egress). */
  local: boolean;
  baseUrl?: string;
  models: Model[];
  latencyMs?: number;
}
