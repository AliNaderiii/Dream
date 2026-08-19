/** Shared type definitions for the Dream desktop shell. */

/** Lifecycle of the Dream agent. Mirrors `state::AgentStatus` in Rust. */
export type AgentStatus = 'idle' | 'running' | 'paused' | 'error' | 'offline';

/** UI colour theme. `system` follows the OS preference. */
export type ThemeMode = 'light' | 'dark' | 'system';

/** Resolved theme actually applied to the DOM (never `system`). */
export type ResolvedTheme = 'light' | 'dark';

/** Writing direction. Persian/Arabic render right-to-left. */
export type Direction = 'ltr' | 'rtl';

/** UI language. Only Persian renders right-to-left. */
export type Locale = 'en' | 'fa' | 'zh-CN' | 'ja' | 'es' | 'de' | 'fr' | 'ko';

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

/** Status of a tool call rendered as a card in the transcript. */
export type ToolCardStatus = 'pending' | 'ok' | 'error' | 'blocked';

/** One tool call rendered as a card inside the conversation transcript. */
export interface ToolCardEntry {
  id: string;
  name: string;
  argsSummary: string;
  status: ToolCardStatus;
  resultExcerpt: string;
  /** Only set when the tool is dangerous and requires approval. */
  approvalId?: string;
}

/** A single message in a conversation. Expanded in P-02, S07. */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: number;
  /** Tool-call cards that precede or accompany this message (S07). */
  toolCards?: ToolCardEntry[];
}

/** A conversation session. */
export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  projectId?: string;
}

/** Kind of model provider Dream can talk to. */
export type ProviderKind =
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'groq'
  | 'together'
  | 'openrouter'
  | 'ollama'
  | 'vllm'
  | 'llamacpp'
  | 'echo';

/** Connection state of a provider, shown in the status bar and provider list. */
export type ProviderStatus = 'connected' | 'disconnected' | 'testing' | 'error';

/** A single model exposed by a provider. */
export interface Model {
  id: string;
  name: string;
  providerId: string;
  contextWindow?: number;
}

/** A configured model provider. Secrets are intentionally absent. */
export interface Provider {
  id: string;
  name: string;
  kind: ProviderKind;
  status: ProviderStatus;
  /** True when the provider runs on this machine (no network egress). */
  local: boolean;
  endpoint?: string;
  modelListUrl?: string;
  models: Model[];
  enabledModelIds: string[];
  credentialConfigured?: boolean;
  supportsReasoning?: boolean;
  supportsStreaming?: boolean;
  latencyMs?: number;
}

export interface ProviderCatalogEntry {
  id: Exclude<ProviderKind, 'echo'>;
  name: string;
  website: string;
  docs?: string;
  authType: 'api_key' | 'none' | 'custom';
  endpoint: string;
  modelListUrl: string | null;
  supportsStreaming: boolean;
  supportsReasoning: boolean;
  defaultModels: string[];
  oauthSupported?: boolean;
}

// ---------------------------------------------------------------------------
// P-08: Docker sandbox / Browser / Gateway UI types
// ---------------------------------------------------------------------------

/** Sandbox feature state. */
export type SandboxState = 'unavailable' | 'available' | 'error' | 'disabled';

/** Browser feature state. */
export type BrowserState = 'offline' | 'attached' | 'isolated' | 'unavailable';

/** Approval decision scope for a tool (S07). */
export type ApprovalDecision = 'allow_once' | 'allow_always_session' | 'deny';

/** A pending approval request shown as a dialog (S07). */
export interface PendingApproval {
  approvalId: string;
  toolName: string;
  argsSummary: string;
  risk: string;
  paneId: string;
}

/** Gateway feature state. */
export type GatewayState = 'stopped' | 'running' | 'error' | 'disabled';
