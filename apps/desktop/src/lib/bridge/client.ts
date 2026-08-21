/**
 * The Dream bridge RPC client.
 *
 * `BridgeClient` speaks JSON-RPC 2.0 to the Python sidecar through a
 * `BridgeTransport`. Two transports ship:
 *
 * - `TauriBridgeTransport` — the real path: the Rust supervisor exposes a
 *   `bridge_send(id, method, params)` command and emits `bridge://chunk` /
 *   `bridge://state` events. Used under Tauri.
 * - `EchoBridgeTransport` — an in-memory fallback so the UI works in `npm run
 *   dev` and unit tests with no sidecar running.
 *
 * The client generates request ids, routes stream chunks by id, tracks
 * connection state, and re-emits everything through a tiny event emitter so
 * React hooks (`useBridge`) can subscribe.
 */

import { invoke as tauriInvoke } from '@tauri-apps/api/core';

import { listen } from '@/lib/tauri';
import { isTauri } from '@/utils/platform';

import { EchoDataRuntime } from './echo-data';
import { EchoCommerceRuntime } from './echo-commerce';
import { EchoGatewayRuntime, requireGatewayPlatform } from './echo-gateway';
import { EchoProjectsRuntime } from './echo-projects';
import { EchoScheduleRuntime, EchoSubagentRuntime } from './echo-subagents';
import { BridgeRpcError, toBridgeError } from './errors';
import {
  normalizeBridgeState,
  type BridgeConnectionState,
  type GatewayPlatformName,
  type RpcId,
  type RpcParams,
  type StreamChunk,
} from './types';

/** Events the client re-emits for hooks/components. */
export type BridgeClientEvent =
  | { type: 'state'; state: BridgeConnectionState }
  | { type: 'error'; error: BridgeRpcError }
  | { type: 'chunk'; chunk: StreamChunk };

type EventHandler = (event: BridgeClientEvent) => void;

/** Callbacks for an in-flight streaming request. */
export interface StreamHandlers {
  onChunk?: (chunk: StreamChunk) => void;
}

/**
 * A transport carries one request at a time and reports state changes.
 * Implementations: `TauriBridgeTransport` (sidecar) and `EchoBridgeTransport`
 * (browser fallback).
 */
export interface BridgeTransport {
  readonly kind: 'tauri' | 'echo';
  /** Execute one request; for streaming methods, `onChunk` fires per chunk. */
  request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T>;
  /** Subscribe to connection-state transitions. Returns an unsubscribe. */
  onState(handler: (state: BridgeConnectionState) => void): () => void;
  /** Ask the supervisor to reconnect/restart the sidecar (no-op for echo). */
  reconnect(): void;
}

// --------------------------------------------------------------------------- //
// Tauri transport — talks to the Rust bridge supervisor.
// --------------------------------------------------------------------------- //

const CHUNK_EVENT = 'bridge://chunk';
const STATE_EVENT = 'bridge://state';

export class TauriBridgeTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  private stateHandlers = new Set<(s: BridgeConnectionState) => void>();

  constructor() {
    void this.wireState();
  }

  private async wireState(): Promise<void> {
    // The listener lives for the app lifetime; Tauri dedupes on window close.
    // The Rust supervisor emits the `ConnectionState` enum directly — a bare
    // JSON string such as `"restarting"` — so we normalise first and never
    // read `.state` off a string payload (which would be `undefined`).
    await listen<unknown>(STATE_EVENT, (payload) => {
      const state = normalizeBridgeState(payload);
      for (const handler of this.stateHandlers) handler(state);
    });
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  reconnect(): void {
    void tauriInvoke('bridge_restart').catch(() => {
      /* supervisor may be mid-restart; ignore */
    });
  }

  async request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    let unlisten: (() => void) | undefined;
    if (onChunk) {
      // Route only the chunks whose id matches this request.
      unlisten = await listen<StreamChunk>(CHUNK_EVENT, (chunk) => {
        if (chunk.id === id) onChunk(chunk);
      });
    }
    try {
      // The Rust command returns the JSON-RPC `result` value, or throws a
      // structured {code, message, data?} error serialised by Tauri.
      return await tauriInvoke<T>('bridge_send', { id, method, params });
    } catch (err) {
      throw toBridgeError(err);
    } finally {
      unlisten?.();
    }
  }
}

// --------------------------------------------------------------------------- //
// Echo transport — browser/test fallback (no sidecar).
// --------------------------------------------------------------------------- //

/** Splits text into token-sized fragments, mirroring `dream.bridge.tokenise`. */
export function tokenise(text: string, maxChars = 12): string[] {
  if (!text) return [];
  const parts = text.match(/\S+\s*|\s+/g) ?? [text];
  const out: string[] = [];
  for (const word of parts) {
    if (word.length <= maxChars) out.push(word);
    else for (let i = 0; i < word.length; i += maxChars) out.push(word.slice(i, i + maxChars));
  }
  return out;
}

interface EchoSession {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  provider: string;
}

/** Shape of the memory rows the echo store keeps (mirrors `BridgeMemory`). */
interface EchoMemory {
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

/** Shape of the skill rows the echo store keeps. */
interface EchoSkill {
  name: string;
  description: string;
  steps: string[];
  filename: string;
  enabled: boolean;
  created_at: number;
}

let echoCounter = 0;

const BROWSER_PROVIDER_CATALOG = {
  openai: {
    name: 'OpenAI',
    website: 'https://platform.openai.com',
    auth_type: 'api_key',
    endpoint: 'https://api.openai.com/v1',
    model_list_url: 'https://api.openai.com/v1/models',
    supports_streaming: true,
    supports_reasoning: true,
    default_models: ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o4-mini'],
  },
  anthropic: {
    name: 'Anthropic',
    website: 'https://console.anthropic.com',
    auth_type: 'api_key',
    endpoint: 'https://api.anthropic.com',
    model_list_url: null,
    supports_streaming: true,
    supports_reasoning: true,
    default_models: ['claude-sonnet-4-20250514', 'claude-haiku-3-5-20241022'],
  },
  google: {
    name: 'Google AI',
    website: 'https://aistudio.google.com',
    auth_type: 'api_key',
    endpoint: 'https://generativelanguage.googleapis.com/v1beta',
    model_list_url: 'https://generativelanguage.googleapis.com/v1beta/models',
    supports_streaming: true,
    supports_reasoning: false,
    oauth_supported: true,
    default_models: ['gemini-2.5-pro', 'gemini-2.5-flash'],
  },
  groq: {
    name: 'Groq',
    website: 'https://console.groq.com',
    auth_type: 'api_key',
    endpoint: 'https://api.groq.com/openai/v1',
    model_list_url: 'https://api.groq.com/openai/v1/models',
    supports_streaming: true,
    supports_reasoning: false,
    default_models: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'],
  },
  together: {
    name: 'Together AI',
    website: 'https://api.together.xyz',
    auth_type: 'api_key',
    endpoint: 'https://api.together.xyz/v1',
    model_list_url: 'https://api.together.xyz/v1/models',
    supports_streaming: true,
    supports_reasoning: false,
    default_models: ['meta-llama/Llama-3.3-70B-Instruct-Turbo'],
  },
  openrouter: {
    name: 'OpenRouter',
    website: 'https://openrouter.ai',
    auth_type: 'api_key',
    endpoint: 'https://openrouter.ai/api/v1',
    model_list_url: 'https://openrouter.ai/api/v1/models',
    supports_streaming: true,
    supports_reasoning: true,
    default_models: [],
  },
  ollama: {
    name: 'Ollama (Local)',
    website: 'https://ollama.com',
    auth_type: 'none',
    endpoint: 'http://localhost:11434/v1',
    model_list_url: 'http://localhost:11434/v1/models',
    supports_streaming: true,
    supports_reasoning: false,
    default_models: [],
  },
  vllm: {
    name: 'vLLM (Custom)',
    website: 'https://docs.vllm.ai',
    auth_type: 'custom',
    endpoint: '',
    model_list_url: '',
    supports_streaming: true,
    supports_reasoning: false,
    default_models: [],
  },
  llamacpp: {
    name: 'llama.cpp (Local)',
    website: 'https://github.com/ggerganov/llama.cpp',
    auth_type: 'none',
    endpoint: 'http://localhost:8080/v1',
    model_list_url: 'http://localhost:8080/v1/models',
    supports_streaming: true,
    supports_reasoning: false,
    default_models: [],
  },
} as const;

function wireString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

interface EchoProviderConfig {
  id: string;
  kind: string;
  name: string;
  endpoint: string;
  model_list_url?: string;
  models: string[];
  enabled_models: string[];
  local: boolean;
  status: string;
  credential_configured: boolean;
  supports_reasoning: boolean;
  supports_streaming: boolean;
}

const DAY_SECONDS = 86_400;

/** Reads a string param, falling back when it is absent or the wrong type. */
function readString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

/** Reads a numeric param, falling back when it is absent or the wrong type. */
function readNumber(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number.NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** A small, deterministic memory corpus so the explorer has something to show. */
function seedMemories(): EchoMemory[] {
  const now = Math.floor(Date.now() / 1000);
  const seeds: Array<[string, string, number, number, string[]]> = [
    [
      'semantic',
      'Dream stores memories as semantic, episodic and procedural rows.',
      0.9,
      0,
      ['core'],
    ],
    [
      'semantic',
      'The bridge speaks JSON-RPC 2.0 over stdio to the Python sidecar.',
      0.8,
      1,
      ['bridge'],
    ],
    ['episodic', 'Reviewed the P-05 memory explorer wireframes this morning.', 0.5, 1, ['design']],
    ['episodic', 'Paired on the skills import validation rules.', 0.4, 3, ['skills']],
    [
      'procedural',
      'To export a skill: open Skills, select it, then choose Export.',
      0.7,
      4,
      ['howto'],
    ],
    ['semantic', 'کاربر زبان فارسی را برای رابط کاربری ترجیح می‌دهد.', 0.6, 5, ['locale']],
    ['episodic', 'Shipped the JSON-RPC sidecar supervisor in P-02.', 0.6, 9, ['release']],
    [
      'procedural',
      'Run npm run typecheck before every commit to the desktop app.',
      0.85,
      12,
      ['howto'],
    ],
    ['semantic', 'Importance is stored 0.0–1.0 and rendered as ten stars.', 0.3, 20, ['ui']],
    ['episodic', 'Investigated a flaky reconnect test in the bridge suite.', 0.2, 33, ['bug']],
  ];
  return seeds.map(([kind, content, importance, daysAgo, tags], index) => ({
    id: index + 1,
    kind,
    content,
    tags,
    importance,
    created_at: now - daysAgo * DAY_SECONDS,
    last_used_at: now - daysAgo * DAY_SECONDS,
    use_count: 0,
    source: 'echo',
    archived: false,
    pinned: false,
    score: 0,
  }));
}

/** Two example skills so the manager renders without a sidecar. */
function seedSkills(): EchoSkill[] {
  const now = Math.floor(Date.now() / 1000);
  return [
    {
      name: 'weekly report',
      description: 'Summarise the week from the session log.',
      steps: ['Collect sessions from the past 7 days', 'Group them by project', 'Write a summary'],
      filename: 'skills/weekly-report.txt',
      enabled: true,
      created_at: now - 6 * DAY_SECONDS,
    },
    {
      name: 'triage inbox',
      description: 'Sort incoming notes into projects.',
      steps: ['Read each unfiled note', 'Match it to a project', 'Move or archive it'],
      filename: 'skills/triage-inbox.txt',
      enabled: false,
      created_at: now - 20 * DAY_SECONDS,
    },
  ];
}

/** Renders an echo skill back to its file body, matching the sidecar's format. */
function renderEchoSkill(skill: EchoSkill): string {
  return [
    `name: ${skill.name}`,
    `description: ${skill.description}`,
    'steps:',
    ...skill.steps.map((step) => `- ${step}`),
    '',
  ].join('\n');
}

/** Very small skill-file parser used by the echo `skill.install` handler. */
function parseEchoSkill(
  content: string,
): { name: string; description: string; steps: string[] } | null {
  let name = '';
  let description = '';
  const steps: string[] = [];
  let inSteps = false;
  for (const raw of content.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const lower = line.toLowerCase();
    if (lower.startsWith('name:')) {
      name = line.slice(5).trim();
      inSteps = false;
    } else if (lower.startsWith('description:')) {
      description = line.slice(12).trim();
      inSteps = false;
    } else if (lower.startsWith('steps:')) {
      inSteps = true;
    } else if (inSteps) {
      steps.push(line.replace(/^[-*]\s*/, '').replace(/^\d+[.)]\s*/, ''));
    }
  }
  if (!name || !description || steps.length === 0) return null;
  return { name, description, steps };
}

/**
 * An in-memory transport that answers a useful subset of methods locally, so
 * the conversation UI is exercisable in a browser without the Python sidecar.
 * It is intentionally minimal and deterministic.
 */
export class EchoBridgeTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private sessions = new Map<string, EchoSession>();
  private providers = new Map<string, EchoProviderConfig>();
  private stateHandlers = new Set<(s: BridgeConnectionState) => void>();
  private startedAt = Date.now();
  private memories: EchoMemory[] = seedMemories();
  private skills: EchoSkill[] = seedSkills();
  private nextMemoryId = this.memories.length + 1;
  private subagents = new EchoSubagentRuntime();
  private schedules = new EchoScheduleRuntime();
  // Projects may only group sessions the echo transport actually knows.
  private projects = new EchoProjectsRuntime((sessionId) => this.sessions.has(sessionId));
  private gateway = new EchoGatewayRuntime();
  private data = new EchoDataRuntime();
  private commerce = new EchoCommerceRuntime();

  /** Stops any simulated subagent still ticking (vitest teardown). */
  dispose(): void {
    this.subagents.dispose();
    this.gateway.dispose();
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  reconnect(): void {
    /* no-op: the echo transport is always ready. */
  }

  async request<T>(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    // Yield once so callers observing async ordering in tests stay deterministic.
    await Promise.resolve();
    return this.handle(id, method, params, onChunk) as Promise<T>;
  }

  private async handle(
    id: RpcId,
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<unknown> {
    // P-09: data science workbench + notebooks live in their own runtime.
    if (this.data.handles(method)) {
      return this.data.handle(method, params);
    }
    switch (method) {
      case 'session.create': {
        const sid = `echo-${++echoCounter}`;
        const now = Date.now();
        this.sessions.set(sid, {
          id: sid,
          title: (params['title'] as string) || 'New session',
          created_at: now,
          updated_at: now,
          message_count: 0,
          provider: 'echo',
        });
        return { session_id: sid, id: sid, title: this.sessions.get(sid)!.title, created_at: now };
      }
      case 'session.list':
        return {
          sessions: [...this.sessions.values()].sort((a, b) => b.updated_at - a.updated_at),
        };
      case 'session.get':
        return this.sessions.get(params['session_id'] as string) ?? null;
      case 'session.delete':
        this.sessions.delete(params['session_id'] as string);
        return { deleted: true };
      case 'session.rename': {
        const s = this.sessions.get(params['session_id'] as string);
        if (s) {
          s.title = (params['title'] as string) || s.title;
          s.updated_at = Date.now();
        }
        return s ?? null;
      }
      case 'session.configure': {
        const s = this.sessions.get(params['session_id'] as string);
        if (s) {
          s.provider = (params['provider'] as string) || s.provider;
          s.updated_at = Date.now();
        }
        return s ?? null;
      }
      case 'conversation.send': {
        const message = (params['message'] as string) ?? '';
        const reply = `Echo: ${message}`;
        for (const token of tokenise(reply)) {
          onChunk?.({ id, token });
          await Promise.resolve();
        }
        const s = this.sessions.get(params['session_id'] as string);
        if (s) {
          s.message_count += 1;
          s.updated_at = Date.now();
        }
        return {
          reply,
          tool_calls: [],
          memories_used: [],
          memories_injected_ids: [],
          memories_created: [],
          memories_superseded: [],
          memories_merged: [],
          elapsed_seconds: 0,
          extraction: { status: 'disabled', facts: [], raw_text: '' },
          memory_errors: [],
        };
      }
      case 'conversation.stop':
        return { stopped: true };
      case 'provider.catalog':
        return { catalog: BROWSER_PROVIDER_CATALOG };
      case 'provider.list':
        return {
          providers: [
            {
              id: 'echo',
              kind: 'echo',
              name: 'Echo (offline)',
              local: true,
              status: 'connected',
              models: ['echo'],
              enabled_models: ['echo'],
              credential_configured: true,
              supports_reasoning: false,
              supports_streaming: true,
            },
            ...this.providers.values(),
          ],
          default: 'echo',
        };
      case 'provider.get':
        return { provider: this.providers.get(params['id'] as string) ?? null };
      case 'provider.create':
      case 'provider.update': {
        const draft = (params['provider'] ?? {}) as Record<string, unknown>;
        const requestedKind = wireString(draft['kind'], 'openai');
        const kind = (
          requestedKind in BROWSER_PROVIDER_CATALOG ? requestedKind : 'openai'
        ) as keyof typeof BROWSER_PROVIDER_CATALOG;
        const catalog = BROWSER_PROVIDER_CATALOG[kind];
        const providerId = wireString(params['id'], `${kind}-${this.providers.size + 1}`);
        const models = (draft['models'] as string[] | undefined) ?? [...catalog.default_models];
        const provider: EchoProviderConfig = {
          id: providerId,
          kind,
          name: wireString(draft['name'], catalog.name),
          endpoint: wireString(draft['endpoint'], catalog.endpoint),
          model_list_url: wireString(draft['model_list_url'], catalog.model_list_url ?? ''),
          models,
          enabled_models: (draft['enabled_models'] as string[] | undefined) ?? models,
          local: kind === 'ollama' || kind === 'llamacpp' || kind === 'vllm',
          status: 'disconnected',
          // Browser preview never retains the credential; this bit only lets the
          // mock UI represent that a value was handed to the sidecar.
          credential_configured:
            Boolean(params['credential']) ||
            this.providers.get(providerId)?.credential_configured === true,
          supports_reasoning: catalog.supports_reasoning,
          supports_streaming: catalog.supports_streaming,
        };
        this.providers.set(providerId, provider);
        return { saved: true, id: providerId, provider, default: 'echo' };
      }
      case 'provider.delete':
        this.providers.delete(params['id'] as string);
        return { deleted: true, id: params['id'], default: 'echo' };
      case 'provider.models': {
        const provider = this.providers.get(params['id'] as string);
        return { provider: params['id'], models: provider?.models ?? [] };
      }
      case 'provider.test': {
        const providerId = (params['id'] ?? params['provider'] ?? 'echo') as string;
        const provider = this.providers.get(providerId);
        if (provider) provider.status = 'connected';
        return { ok: true, provider: providerId, latency_ms: 8 };
      }
      case 'memory.list':
        return this.echoMemoryList(params);
      case 'memory.count': {
        const active = this.memories.filter((m) => !m.archived);
        const byKind: Record<string, number> = { semantic: 0, episodic: 0, procedural: 0 };
        for (const m of active) byKind[m.kind] = (byKind[m.kind] ?? 0) + 1;
        return {
          total: active.length,
          by_kind: byKind,
          archived: this.memories.length - active.length,
        };
      }
      case 'memory.search': {
        const query = readString(params['query']).toLowerCase();
        const limit = readNumber(params['limit'], 8);
        return {
          memories: this.memories
            .filter((m) => !m.archived && m.content.toLowerCase().includes(query))
            .slice(0, limit),
        };
      }
      case 'memory.get':
        return this.memories.find((m) => m.id === readNumber(params['memory_id'], -1)) ?? null;
      case 'memory.create': {
        const now = Math.floor(Date.now() / 1000);
        const memory: EchoMemory = {
          id: this.nextMemoryId++,
          kind: readString(params['kind'], 'semantic'),
          content: readString(params['content']),
          tags: Array.isArray(params['tags']) ? (params['tags'] as string[]) : [],
          importance: readNumber(params['importance'], 0.5),
          created_at: now,
          last_used_at: now,
          use_count: 0,
          source: readString(params['source'], 'desktop'),
          archived: false,
          pinned: false,
          score: 0,
        };
        this.memories.unshift(memory);
        return { memory };
      }
      case 'memory.update': {
        const memory = this.memories.find((m) => m.id === readNumber(params['memory_id'], -1));
        if (!memory) {
          throw new BridgeRpcError({ code: -32602, message: 'no such memory' });
        }
        if (typeof params['content'] === 'string') memory.content = params['content'];
        if (typeof params['kind'] === 'string') memory.kind = params['kind'];
        if (typeof params['importance'] === 'number') memory.importance = params['importance'];
        if (Array.isArray(params['tags'])) memory.tags = params['tags'] as string[];
        return { memory };
      }
      case 'memory.delete': {
        const memoryId = readNumber(params['memory_id'], -1);
        const memory = this.memories.find((m) => m.id === memoryId);
        if (!memory) {
          throw new BridgeRpcError({ code: -32602, message: 'no such memory' });
        }
        if (params['hard']) this.memories = this.memories.filter((m) => m.id !== memoryId);
        else memory.archived = true;
        return { deleted: true, memory_id: memoryId };
      }
      case 'skill.list':
        return {
          skills: this.skills.map((s) => ({
            name: s.name,
            description: s.description,
            steps: s.steps,
            filename: s.filename,
            enabled: s.enabled,
          })),
          problems: [],
        };
      case 'skill.get': {
        const skill = this.findEchoSkill(params['skill_id'] ?? params['query']);
        if (!skill) return { match: null };
        return { match: { ...skill, content: renderEchoSkill(skill) } };
      }
      case 'skill.install': {
        const content = readString(params['content']);
        const parsed = parseEchoSkill(content);
        if (!parsed) {
          throw new BridgeRpcError({ code: -32602, message: 'invalid skill file' });
        }
        const name = readString(params['name'], parsed.name);
        const existing = this.skills.find((s) => s.name === name);
        if (existing && !params['overwrite']) {
          return {
            filename: existing.filename,
            status: 'conflict',
            name: existing.name,
            conflict: true,
            existing_filename: existing.filename,
          };
        }
        const filename = `skills/${name.replace(/\s+/g, '-').toLowerCase()}.txt`;
        const record: EchoSkill = {
          name,
          description: parsed.description,
          steps: parsed.steps,
          filename,
          enabled: existing?.enabled ?? true,
          created_at: Math.floor(Date.now() / 1000),
        };
        if (existing) Object.assign(existing, record);
        else this.skills.push(record);
        return { filename, status: 'installed', name };
      }
      case 'skill.delete':
      case 'skill.remove': {
        const skill = this.findEchoSkill(params['skill_id'] ?? params['name']);
        if (!skill) {
          throw new BridgeRpcError({ code: -32602, message: 'no such skill' });
        }
        this.skills = this.skills.filter((s) => s !== skill);
        return { deleted: true, removed: true, filename: skill.filename, name: skill.name };
      }
      case 'skill.enable':
      case 'skill.disable': {
        const skill = this.findEchoSkill(params['skill_id'] ?? params['name']);
        if (!skill) {
          throw new BridgeRpcError({ code: -32602, message: 'no such skill' });
        }
        skill.enabled = method === 'skill.enable';
        return { name: skill.name, filename: skill.filename, enabled: skill.enabled };
      }
      case 'skill.export': {
        const skill = this.findEchoSkill(params['skill_id'] ?? params['name']);
        if (!skill) {
          throw new BridgeRpcError({ code: -32602, message: 'no such skill' });
        }
        return { name: skill.name, filename: skill.filename, content: renderEchoSkill(skill) };
      }
      case 'tool.list':
        return {
          tools: [
            { name: 'calculate', risk: 'safe', description: 'Evaluate arithmetic', schema: {} },
            { name: 'get_datetime', risk: 'safe', description: 'Current date/time', schema: {} },
            { name: 'remember_fact', risk: 'safe', description: 'Store a fact', schema: {} },
            { name: 'search_memory', risk: 'safe', description: 'Search memory', schema: {} },
            { name: 'read_file', risk: 'guarded', description: 'Read a file', schema: {} },
            { name: 'write_file', risk: 'dangerous', description: 'Write a file', schema: {} },
          ],
        };
      // -- subagents ----------------------------------------------------- //
      case 'subagent.spawn':
        return this.subagents.spawn(params);
      case 'subagent.pipeline':
        return this.subagents.spawnPipeline(params);
      case 'subagent.list':
        return this.subagents.list(params);
      case 'subagent.get':
      case 'subagent.status':
        return this.subagents.get(params);
      case 'subagent.cancel':
        return this.subagents.cancel(params);
      case 'subagent.pause':
        return this.subagents.pause(params);
      case 'subagent.resume':
        return this.subagents.resume(params);
      case 'subagent.logs':
        // Matches the sidecar: a chunk per log line, then the final agent.
        return this.subagents.follow(params, (entry, subagentId) => {
          onChunk?.({
            id,
            token: entry.message,
            event: 'log',
            subagent_id: subagentId,
            entry,
          });
        });
      case 'council.run':
        return this.subagents.runCouncil(params);
      case 'council.get':
        return this.subagents.getCouncil(params);

      // -- schedules ------------------------------------------------------ //
      case 'schedule.create':
        return this.schedules.create(params);
      case 'schedule.list':
        return this.schedules.list(params);
      case 'schedule.get':
        return this.schedules.get(params);
      case 'schedule.update':
        return this.schedules.update(params);
      case 'schedule.delete':
        return this.schedules.delete(params);
      case 'schedule.toggle':
        return this.schedules.toggle(params);
      case 'schedule.history':
        return this.schedules.history(params);
      case 'schedule.preview':
        return this.schedules.preview(params);
      case 'schedule.run_now':
        return this.schedules.runNow(params);

      // -- projects (S06) -------------------------------------------------- //
      case 'project.create':
        return this.projects.create(params);
      case 'project.list':
        return this.projects.list(params);
      case 'project.get':
        return this.projects.get(params);
      case 'project.update':
        return this.projects.update(params);
      case 'project.delete':
        return this.projects.delete(params);
      case 'project.add_session':
        return this.projects.addSession(params);
      case 'project.remove_session':
        return this.projects.removeSession(params);

      // -- approvals (S06) ------------------------------------------------- //
      // The echo transport never holds a pending approval: its run-now path
      // denies approval-required runs outright (fail-closed, gate G11).
      case 'approval.list':
        return { approvals: [] };

      // -- connectivity gateway ------------------------------------------ //
      case 'gateway.platforms':
        return { platforms: this.gateway.platforms() };
      case 'gateway.status':
        return this.gateway.status();
      case 'gateway.start':
        return this.gateway.start();
      case 'gateway.stop':
        return this.gateway.stop();
      case 'gateway.configure': {
        const platform = requireGatewayPlatform(params);
        const values = params['config'];
        if (!values || typeof values !== 'object' || Array.isArray(values)) {
          throw new BridgeRpcError({ code: -32602, message: 'config must be an object' });
        }
        const config = this.gateway.configure(platform, values as Record<string, unknown>);
        return { saved: true, platform, config };
      }
      case 'gateway.logs': {
        const rawPlatform = params['platform'];
        const platform =
          typeof rawPlatform === 'string' ? (rawPlatform as GatewayPlatformName) : null;
        const limit = typeof params['limit'] === 'number' ? params['limit'] : null;
        return this.gateway.logs(platform, limit);
      }
      case 'gateway.link_code': {
        const platform = requireGatewayPlatform(params);
        return this.gateway.linkCode(platform);
      }
      case 'gateway.linked_users': {
        const rawPlatform = params['platform'];
        const platform = typeof rawPlatform === 'string' ? rawPlatform : null;
        return { linked_users: this.gateway.linkedUsers(platform) };
      }
      case 'gateway.unlink_user': {
        const platform = requireGatewayPlatform(params);
        const userId = readString(params['user_id']);
        if (!userId) {
          throw new BridgeRpcError({ code: -32602, message: 'user_id must be a non-empty string' });
        }
        return { unlinked: this.gateway.unlinkUser(platform, userId), platform, user_id: userId };
      }

      case 'health.check':
        return {
          status: 'ok',
          sessions: this.sessions.size,
          provider: 'echo',
          uptime_seconds: (Date.now() - this.startedAt) / 1000,
        };
      case 'sidecar.version':
        return { protocol: '1.0', core: '0.1.0', sidecar: '0.1.0', python: 'browser' };
      // P-08: Docker sandbox echo stubs.
      case 'sandbox.status':
        return { available: false, docker: false, error: 'Docker not available in echo mode' };
      case 'sandbox.run_code':
        return {
          stdout: 'Echo sandbox: code execution not available',
          stderr: '',
          return_code: -1,
          timed_out: false,
          output_files: [],
          elapsed_seconds: 0,
          error: 'Sandbox is not available in echo mode. Start the sidecar with Docker installed.',
        };
      case 'sandbox.run_notebook':
      case 'sandbox.install_packages':
        return { error: 'Sandbox not available in echo mode' };

      // P-08: Browser control echo stubs.
      case 'browser.attach':
      case 'browser.launch_isolated':
        return { error: 'Browser control not available in echo mode', mode: 'echo' };
      case 'browser.request_approval':
        return {
          session_id: `echo-${++echoCounter}`,
          url: params['url'] as string,
          purpose: (params['purpose'] as string) || '',
          domain: 'echo.local',
          status: 'pending',
        };
      case 'browser.approve':
      case 'browser.deny':
        return { approved: true, session_id: params['session_id'] as string };
      case 'browser.navigate':
        return {
          url: params['url'] as string,
          title: 'Echo Page',
          text: 'Echo transport: page content not available',
          links: [],
          tables: [],
        };
      case 'browser.get_content':
        return { url: '', title: 'Echo', text: '', links: [], tables: [] };
      case 'browser.execute_js':
        return null;
      case 'browser.fill_form':
      case 'browser.click':
        return { success: true };
      case 'browser.screenshot':
        return { screenshot_path: '' };
      case 'browser.get_cookies':
        return { cookies: [] };
      case 'browser.status':
        return {
          attached: false,
          attached_to_existing: false,
          has_page: false,
          pending_approvals: 0,
          approved_domains: [],
          current_session: null,
          screenshot_dir: '',
        };
      case 'browser.close':
        return { closed: true };

      // P-08: Web gateway echo stubs.
      case 'gateway.get_tokens':
        return { tokens: {} };
      case 'gateway.create_token':
        return {
          token: `drm_echo_${Date.now()}`,
          scope: 'write',
          label: params['label'] as string,
        };
      case 'gateway.rotate_token':
        return { token: `drm_echo_${Date.now()}`, rotated: true };
      case 'gateway.revoke_token':
        return { revoked: true };

      // P-10: Provenance echo stubs.
      case 'provenance.list':
        return {
          records: [
            {
              record_id: 'prov_demo_01',
              timestamp: new Date().toISOString(),
              event_type: 'tool_call',
              agent_id: 'sess_demo',
              payload: { tool_name: 'generate_figure', arguments: { kind: 'bar_chart' } },
              input_snapshot: [
                { path: 'data/sales.csv', hash: 'abc1234', size: 1024, modified_at: Date.now() },
              ],
              output_snapshot: [
                {
                  path: 'reports/sales_chart.png',
                  hash: 'def5678',
                  size: 24500,
                  modified_at: Date.now(),
                },
              ],
              model_snapshot: { provider: 'echo', model: 'echo-v1' },
              duration_ms: 250,
              token_count: 45,
              prev_hash: '0'.repeat(64),
              hash: 'sha256_mock_hash_01',
            },
            {
              record_id: 'prov_demo_02',
              timestamp: new Date(Date.now() - 60000).toISOString(),
              event_type: 'user_message',
              agent_id: 'sess_demo',
              payload: { message: 'Plot the Q3 sales performance chart.' },
              input_snapshot: [],
              output_snapshot: [],
              prev_hash: '0'.repeat(64),
              hash: 'sha256_mock_hash_02',
            },
          ],
          total: 2,
        };
      case 'provenance.get':
        return {
          record_id: params['record_id'] ?? 'prov_demo_01',
          timestamp: new Date().toISOString(),
          event_type: 'tool_call',
          agent_id: 'sess_demo',
          payload: { tool_name: 'generate_figure' },
          input_snapshot: [],
          output_snapshot: [],
          hash: 'sha256_mock_hash',
        };
      case 'provenance.tree':
        return {
          nodes: [
            {
              id: 'node_1',
              label: 'user_message: Plot Q3 sales chart',
              event_type: 'user_message',
              agent_id: 'sess_demo',
              timestamp: new Date().toISOString(),
              payload: {},
              inputs: [],
              outputs: [],
            },
            {
              id: 'node_2',
              label: 'tool_call: generate_figure',
              event_type: 'tool_call',
              agent_id: 'sess_demo',
              timestamp: new Date().toISOString(),
              duration_ms: 120,
              payload: { tool_name: 'generate_figure' },
              inputs: [
                { path: 'data/sales.csv', hash: 'abc1234', size: 1024, modified_at: Date.now() },
              ],
              outputs: [
                {
                  path: 'reports/sales_chart.png',
                  hash: 'def5678',
                  size: 24500,
                  modified_at: Date.now(),
                },
              ],
            },
          ],
          edges: [{ source: 'node_1', target: 'node_2', type: 'parent_child' }],
          count: 2,
        };
      case 'provenance.verify':
        return { valid: true, records_checked: 42, broken_at: null, error: null };
      case 'provenance.export':
        return {
          filename: 'dream_reproducibility_export.zip',
          size: 14200,
          records_count: 2,
          base64_data: 'UEsDBBQAAAAIA...',
        };
      case 'artifact.get':
        return {
          artifact_path: (params['path'] as string) || 'reports/sales_chart.png',
          exists: true,
          size: 24500,
          hash: 'def5678',
          record_id: 'prov_demo_01',
          tool_name: 'generate_figure',
          agent_id: 'sess_demo',
          created_at: new Date().toISOString(),
          model: 'echo-v1',
          lineage_statement:
            'This artifact was generated by generate_figure in session sess_demo using model echo-v1',
        };
      case 'artifact.list':
        return {
          artifacts: [
            {
              artifact_path: 'reports/sales_chart.png',
              exists: true,
              size: 24500,
              hash: 'def5678',
              record_id: 'prov_demo_01',
              tool_name: 'generate_figure',
              agent_id: 'sess_demo',
              created_at: new Date().toISOString(),
              model: 'echo-v1',
              lineage_statement:
                'This artifact was generated by generate_figure in session sess_demo using model echo-v1',
            },
          ],
        };
      case 'mcp.list_servers':
        return {
          servers: [
            {
              id: 'mcp_filesystem',
              name: 'Filesystem MCP',
              type: 'stdio',
              command: 'npx',
              args: ['-y', '@modelcontextprotocol/server-filesystem'],
              enabled: true,
              disabled_tools: [],
              status: 'connected',
              is_connected: true,
              tools_count: 5,
              resources_count: 2,
            },
            {
              id: 'mcp_postgres',
              name: 'PostgreSQL MCP',
              type: 'sse',
              url: 'http://localhost:8080/sse',
              enabled: true,
              disabled_tools: [],
              status: 'connected',
              is_connected: true,
              tools_count: 3,
              resources_count: 1,
            },
          ],
        };
      case 'mcp.add_server':
        return {
          id: `mcp_${Date.now()}`,
          name: (params['name'] as string) || 'New Server',
          type: (params['type'] as string) || 'stdio',
          enabled: true,
          disabled_tools: [],
        };
      case 'mcp.remove_server':
        return { removed: true, server_id: params['server_id'] };
      case 'mcp.toggle_server':
        return {
          id: params['server_id'],
          enabled: params['enabled'] ?? true,
        };
      case 'mcp.toggle_tool':
        return { saved: true };
      case 'mcp.test_connection':
        return { ok: true, name: 'Filesystem MCP', tools_count: 5, latency_ms: 12 };
      case 'mcp.list_tools':
        return {
          tools: [
            {
              name: 'read_file',
              description: 'Read the complete contents of a file',
              input_schema: { type: 'object', properties: { path: { type: 'string' } } },
              server_id: 'mcp_filesystem',
              server_name: 'Filesystem MCP',
              enabled: true,
              risk: 'safe',
            },
            {
              name: 'write_file',
              description: 'Write complete contents to a file',
              input_schema: {
                type: 'object',
                properties: { path: { type: 'string' }, content: { type: 'string' } },
              },
              server_id: 'mcp_filesystem',
              server_name: 'Filesystem MCP',
              enabled: true,
              risk: 'guarded',
            },
          ],
        };
      case 'acp.server.status':
        return { status: 'ready', token_configured: true, protocol: 'acp/1.0' };
      case 'acp.server.start':
        return { started: true, token_configured: true };
      case 'acp.server.stop':
        return { stopped: true };
      case 'acp.client.list_agents':
        return {
          agents: [
            {
              id: 'claude_code',
              name: 'Claude Code (ACP)',
              endpoint: 'http://localhost:8001',
              label: 'Claude Code',
              description: 'Anthropic Claude Code agent via local ACP bridge',
              enabled: true,
              status: 'ready',
            },
            {
              id: 'codex_acp',
              name: 'Codex (ACP)',
              endpoint: 'http://localhost:8002',
              label: 'OpenAI Codex',
              description: 'OpenAI Codex programming agent via ACP',
              enabled: true,
              status: 'ready',
            },
            {
              id: 'gemini_cli',
              name: 'Gemini CLI (ACP)',
              endpoint: 'http://localhost:8003',
              label: 'Gemini CLI',
              description: 'Google Gemini CLI assistant via ACP',
              enabled: true,
              status: 'ready',
            },
          ],
        };
      case 'acp.client.add_agent':
        return {
          id: `acp_${Date.now()}`,
          name: (params['name'] as string) || 'New ACP Agent',
          endpoint: (params['endpoint'] as string) || 'http://localhost:8000',
          label: (params['label'] as string) || 'ACP Agent',
          enabled: true,
        };
      case 'acp.client.remove_agent':
        return { removed: true, agent_id: params['agent_id'] };
      case 'acp.client.test_agent':
        return { ok: true, name: 'Claude Code (ACP)', latency_ms: 18, tools_count: 8 };

      // S05: commerce.* / route.* — deterministic plan, usage, and route.
      case 'commerce.plan':
        return this.commerce.plan();
      case 'commerce.usage':
        return this.commerce.usage();
      case 'route.resolve':
        return this.commerce.route();
      default:
        throw new BridgeRpcError({ code: -32601, message: `echo: unknown method ${method}` });
    }
  }

  /** Filter, sort and page the in-memory corpus the way `memory.list` does. */
  private echoMemoryList(params: RpcParams): unknown {
    const rawKinds = params['kind_filter'];
    const kinds =
      rawKinds == null
        ? null
        : Array.isArray(rawKinds)
          ? (rawKinds as string[])
          : [readString(rawKinds)];
    const query = readString(params['search_query']).trim().toLowerCase();
    const dateFrom = params['date_from'] == null ? null : readNumber(params['date_from'], 0);
    const dateTo = params['date_to'] == null ? null : readNumber(params['date_to'], 0);
    const minImportance =
      params['min_importance'] == null ? null : readNumber(params['min_importance'], 0);
    const sortBy = readString(params['sort_by'], 'date_newest');
    const limit = Math.max(1, Math.min(500, readNumber(params['limit'], 50)));
    const cursor = Math.max(0, readNumber(params['cursor'], 0));
    const includeArchived = Boolean(params['include_archived']);

    let rows = this.memories.filter((m) => includeArchived || !m.archived);
    if (kinds) rows = rows.filter((m) => kinds.includes(m.kind));
    if (query) rows = rows.filter((m) => m.content.toLowerCase().includes(query));
    if (dateFrom != null) rows = rows.filter((m) => m.created_at >= dateFrom);
    if (dateTo != null) rows = rows.filter((m) => m.created_at <= dateTo);
    if (minImportance != null) rows = rows.filter((m) => m.importance >= minImportance);

    rows = [...rows];
    if (sortBy === 'date_oldest') rows.sort((a, b) => a.created_at - b.created_at);
    else if (sortBy === 'importance')
      rows.sort((a, b) => b.importance - a.importance || b.created_at - a.created_at);
    else rows.sort((a, b) => b.created_at - a.created_at);

    const page = rows.slice(cursor, cursor + limit);
    const hasMore = cursor + limit < rows.length;
    return {
      memories: page,
      total: rows.length,
      next_cursor: hasMore ? String(cursor + limit) : null,
      has_more: hasMore,
    };
  }

  /** Resolve a skill by bare name or `skills/<slug>.txt` id. */
  private findEchoSkill(idOrName: unknown): EchoSkill | undefined {
    if (typeof idOrName !== 'string' || !idOrName.trim()) return undefined;
    const needle = idOrName.trim();
    return (
      this.skills.find((s) => s.name === needle) ??
      this.skills.find((s) => s.filename === needle) ??
      this.skills.find((s) => s.name.toLowerCase().includes(needle.toLowerCase()))
    );
  }
}

// --------------------------------------------------------------------------- //
// The client.
// --------------------------------------------------------------------------- //

/** Selects the real transport under Tauri, else the echo fallback. */
export function defaultTransport(): BridgeTransport {
  return isTauri() ? new TauriBridgeTransport() : new EchoBridgeTransport();
}

export class BridgeClient {
  private transport: BridgeTransport;
  private nextId = 1;
  private handlers = new Set<EventHandler>();
  private _state: BridgeConnectionState;
  private readonly autoSelect: boolean;
  private readonly tauriTransport: TauriBridgeTransport | null;
  private readonly echoTransport: EchoBridgeTransport;
  private _isUsingFallback = false;

  constructor(transport?: BridgeTransport) {
    this.autoSelect = !transport;
    if (transport) {
      this.transport = transport;
      this.tauriTransport = null;
      this.echoTransport = new EchoBridgeTransport();
    } else {
      this.tauriTransport = isTauri() ? new TauriBridgeTransport() : null;
      this.echoTransport = new EchoBridgeTransport();
      this.transport = this.tauriTransport ?? this.echoTransport;
    }
    this._state = this.transport.kind === 'tauri' ? 'connecting' : 'ready';
    this.transport.onState((state) => this.setState(state));
  }

  /** The current connection state. */
  get state(): BridgeConnectionState {
    return this._state;
  }

  /** Which transport is active — `tauri` (sidecar) or `echo` (browser). */
  get transportKind(): 'tauri' | 'echo' {
    return this.transport.kind;
  }

  /** Subscribe to client events. Returns an unsubscribe. */
  on(handler: EventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  /** Typed request/response. Rejects with `BridgeRpcError` on failure. */
  async call<T>(method: string, params: RpcParams = {}): Promise<T> {
    return this.dispatch<T>(method, params);
  }

  /**
   * Streaming request. `onChunk` fires for each `stream.chunk`; the returned
   * promise resolves with the final result (or rejects with `BridgeRpcError`).
   */
  async stream<T>(method: string, params: RpcParams, handlers: StreamHandlers = {}): Promise<T> {
    return this.dispatch<T>(method, params, (chunk) => {
      this.emit({ type: 'chunk', chunk });
      handlers.onChunk?.(chunk);
    });
  }

  /** Ask the supervisor to restart the sidecar. */
  reconnect(): void {
    this.setState('reconnecting');
    this.transport.reconnect();
    // Also switch back to Tauri transport while reconnecting.
    if (this.tauriTransport && this._isUsingFallback) {
      this.transport = this.tauriTransport;
      this.transport.onState((state) => this.setState(state));
      this._isUsingFallback = false;
    }
  }

  /** Swap the transport (used by tests and by reconnect-with-backoff). */
  setTransport(transport: BridgeTransport): void {
    this.transport = transport;
    this.transport.onState((state) => this.setState(state));
    this.setState(transport.kind === 'tauri' ? 'connecting' : 'ready');
  }

  private async dispatch<T>(
    method: string,
    params: RpcParams,
    onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    const id = this.nextId++;
    try {
      const result = await this.transport.request<T>(id, method, params, onChunk);
      return result;
    } catch (err) {
      const error = toBridgeError(err);
      this.emit({ type: 'error', error });
      throw error;
    }
  }

  private setState(state: BridgeConnectionState): void {
    if (this._state === state) return;

    // S15: When the Tauri transport is disconnected, fall back to Echo so the
    // UI stays usable. When it becomes ready, switch back.
    if (this.tauriTransport && this.echoTransport) {
      if (state === 'ready') {
        // Sidecar came back online — switch away from fallback.
        if (this._isUsingFallback) {
          this.transport = this.tauriTransport;
          this.transport.onState((s) => this.setState(s));
          this._isUsingFallback = false;
        }
      } else if (state === 'disconnected') {
        // Sidecar is down — switch to Echo so basic operations work.
        if (!this._isUsingFallback) {
          this.transport = this.echoTransport;
          this.transport.onState(() => {}); // Echo always stays ready; no-op handler.
          this._isUsingFallback = true;
        }
      }
    }

    this._state = state;
    this.emit({ type: 'state', state });
  }

  private emit(event: BridgeClientEvent): void {
    for (const handler of this.handlers) handler(event);
  }

  /** Whether the auto-selected transport is the echo fallback. */
  get isFallback(): boolean {
    return this.autoSelect && this.transport.kind === 'echo';
  }

  /** Whether we are currently using the Echo fallback due to sidecar being offline. */
  get isUsingFallback(): boolean {
    return this._isUsingFallback;
  }
}

/** A process-wide default client, lazily created. */
let defaultClient: BridgeClient | undefined;

export function getBridgeClient(): BridgeClient {
  if (!defaultClient) defaultClient = new BridgeClient();
  return defaultClient;
}

/** Test helper: reset the singleton (vitest `beforeEach`). */
export function resetBridgeClient(): void {
  defaultClient = undefined;
}
