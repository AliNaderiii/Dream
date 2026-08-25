/**
 * Deterministic echo runtime for the `providerhubs.*` family (P5).
 *
 * Mirrors the planned sidecar contract so the providers page works offline
 * and in tests without a live runtime. Credentials are never stored or
 * returned. Probes are bounded and send no secrets.
 */

export type RuntimeKind = 'ollama' | 'vllm' | 'sglang' | 'llamacpp' | 'lmstudio' | 'generic';

export type ParserFamily =
  | 'function_tools'
  | 'qwen'
  | 'llama3'
  | 'mistral'
  | 'hermes'
  | 'deepseek'
  | 'glm'
  | 'generic_fallback';

export type RuntimeHealth = 'healthy' | 'down' | 'unknown' | 'idle';

export type CostTier = 'local' | 'byok' | 'optional';

export type GatewayToolId = 'web_search' | 'image' | 'tts' | 'browser';

export interface RuntimeRecord {
  id: RuntimeKind;
  name: string;
  endpoint: string;
  detected: boolean;
  health: RuntimeHealth;
  recommended: boolean;
  local: boolean;
  data_leaves_machine: boolean;
  tool_calling: 'native' | 'fallback' | 'disabled';
  parser: ParserFamily;
  parser_guidance: string;
  models: string[];
  selected_model: string;
  cost_tier: CostTier;
  privacy_en: string;
  privacy_fa: string;
  fix_hint: string;
}

export interface CatalogEntry {
  id: string;
  name: string;
  local: boolean;
  runtimes: RuntimeKind[];
  cost_tier: CostTier;
  data_leaves_machine: boolean;
  privacy_en: string;
  privacy_fa: string;
  tool_calling: boolean;
  notes: string;
}

export interface GatewayTool {
  id: GatewayToolId;
  enabled: boolean;
  byok: boolean;
  credential_configured: boolean;
}

export interface GatewayState {
  optional: true;
  enabled: boolean;
  required_for_local: false;
  tools: GatewayTool[];
  auth: 'none' | 'keychain';
}

export interface DiagnoseResult {
  runtime_id: RuntimeKind;
  firing: boolean;
  reason: string;
  reason_fa: string;
  fix: string;
  fix_fa: string;
  reduced_reliability: boolean;
}

export interface ProbeResult {
  runtime_id: RuntimeKind;
  ok: boolean;
  latency_ms: number;
  detail: string;
  secrets_sent: false;
}

export interface RouteSnapshot {
  priority: readonly ['hosted', 'aval', 'ollama', 'byok', 'echo'];
  active: 'echo';
  sentence_en: string;
  sentence_fa: string;
}

export interface ParserInfo {
  id: ParserFamily;
  runtimes: RuntimeKind[];
  native: boolean;
}

const ROUTE_PRIORITY = ['hosted', 'aval', 'ollama', 'byok', 'echo'] as const;

const LOCAL_PRIVACY_EN = 'Data stays on this machine.';
const LOCAL_PRIVACY_FA = 'داده روی همین دستگاه می‌ماند.';
const CLOUD_PRIVACY_EN = 'Requests leave this machine when this route is used.';
const CLOUD_PRIVACY_FA = 'در صورت استفاده از این مسیر، درخواست‌ها این دستگاه را ترک می‌کنند.';

function seedRuntimes(): RuntimeRecord[] {
  return [
    {
      id: 'ollama',
      name: 'Ollama',
      endpoint: 'http://127.0.0.1:11434/v1',
      detected: true,
      health: 'healthy',
      recommended: true,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'native',
      parser: 'function_tools',
      parser_guidance: 'Ollama tool calling is on by default.',
      models: ['llama3.1', 'qwen2.5', 'mistral'],
      selected_model: 'llama3.1',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint: 'Ollama tool calling is on by default.',
    },
    {
      id: 'vllm',
      name: 'vLLM',
      endpoint: 'http://127.0.0.1:8000/v1',
      detected: false,
      health: 'idle',
      recommended: false,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'disabled',
      parser: 'qwen',
      parser_guidance: 'Match the parser to the model family (qwen, mistral, or hermes).',
      models: [],
      selected_model: '',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint:
        'Start vLLM with --enable-auto-tool-choice --tool-call-parser qwen (or the parser that matches your model family).',
    },
    {
      id: 'sglang',
      name: 'SGLang',
      endpoint: 'http://127.0.0.1:30000/v1',
      detected: false,
      health: 'idle',
      recommended: false,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'disabled',
      parser: 'mistral',
      parser_guidance: 'Use --tool-call-parser mistral (or the family that matches the model).',
      models: [],
      selected_model: '',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint:
        'Start SGLang with --tool-call-parser mistral (or the parser that matches your model family).',
    },
    {
      id: 'llamacpp',
      name: 'llama.cpp',
      endpoint: 'http://127.0.0.1:8080/v1',
      detected: false,
      health: 'idle',
      recommended: false,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'disabled',
      parser: 'llama3',
      parser_guidance: 'llama-server needs --jinja so templates emit structured tool calls.',
      models: [],
      selected_model: '',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint: 'Start llama-server with --jinja so templates emit structured tool calls.',
    },
    {
      id: 'lmstudio',
      name: 'LM Studio',
      endpoint: 'http://127.0.0.1:1234/v1',
      detected: false,
      health: 'idle',
      recommended: false,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'disabled',
      parser: 'function_tools',
      parser_guidance: 'Enable structured output / tools in the LM Studio server settings.',
      models: [],
      selected_model: '',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint: 'Enable structured output / tools in the LM Studio server settings.',
    },
    {
      id: 'generic',
      name: 'Generic compatible endpoint',
      endpoint: 'http://127.0.0.1:8000/v1',
      detected: false,
      health: 'unknown',
      recommended: false,
      local: true,
      data_leaves_machine: false,
      tool_calling: 'fallback',
      parser: 'generic_fallback',
      parser_guidance:
        'No native tools. Dream parses structured text with the generic fallback — reliability is lower.',
      models: ['compatible-chat'],
      selected_model: 'compatible-chat',
      cost_tier: 'local',
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      fix_hint:
        'This endpoint has no native tools. Dream will parse structured text with the generic fallback — reliability is lower.',
    },
  ];
}

function seedCatalog(): CatalogEntry[] {
  return [
    {
      id: 'ollama',
      name: 'Ollama',
      local: true,
      runtimes: ['ollama'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: true,
      notes: 'Recommended local default. No VPN. No cloud key.',
    },
    {
      id: 'vllm',
      name: 'vLLM',
      local: true,
      runtimes: ['vllm'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: true,
      notes: 'Local serving stack. Enable the matching tool-call parser.',
    },
    {
      id: 'sglang',
      name: 'SGLang',
      local: true,
      runtimes: ['sglang'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: true,
      notes: 'Local serving stack. Pass --tool-call-parser for your family.',
    },
    {
      id: 'llamacpp',
      name: 'llama.cpp',
      local: true,
      runtimes: ['llamacpp'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: true,
      notes: 'Local llama-server. Use --jinja for structured tools.',
    },
    {
      id: 'lmstudio',
      name: 'LM Studio',
      local: true,
      runtimes: ['lmstudio'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: true,
      notes: 'Local desktop server. Enable tools in its settings.',
    },
    {
      id: 'generic',
      name: 'Generic compatible endpoint',
      local: true,
      runtimes: ['generic'],
      cost_tier: 'local',
      data_leaves_machine: false,
      privacy_en: LOCAL_PRIVACY_EN,
      privacy_fa: LOCAL_PRIVACY_FA,
      tool_calling: false,
      notes: 'Fallback parser. Reduced reliability is shown in the UI.',
    },
    {
      id: 'aval',
      name: 'Aval',
      local: false,
      runtimes: [],
      cost_tier: 'byok',
      data_leaves_machine: true,
      privacy_en: CLOUD_PRIVACY_EN,
      privacy_fa: CLOUD_PRIVACY_FA,
      tool_calling: true,
      notes: 'Bring your own key. Dream does not list a price.',
    },
    {
      id: 'hosted',
      name: 'Hosted',
      local: false,
      runtimes: [],
      cost_tier: 'optional',
      data_leaves_machine: true,
      privacy_en: CLOUD_PRIVACY_EN,
      privacy_fa: CLOUD_PRIVACY_FA,
      tool_calling: true,
      notes: 'Optional hosted route. Price is not invented here.',
    },
  ];
}

function seedGateway(): GatewayState {
  return {
    optional: true,
    enabled: false,
    required_for_local: false,
    auth: 'none',
    tools: [
      { id: 'web_search', enabled: false, byok: true, credential_configured: false },
      { id: 'image', enabled: false, byok: true, credential_configured: false },
      { id: 'tts', enabled: false, byok: true, credential_configured: false },
      { id: 'browser', enabled: false, byok: true, credential_configured: false },
    ],
  };
}

const PARSERS: ParserInfo[] = [
  { id: 'function_tools', runtimes: ['ollama', 'lmstudio', 'generic'], native: true },
  { id: 'qwen', runtimes: ['vllm', 'ollama'], native: true },
  { id: 'llama3', runtimes: ['llamacpp', 'ollama'], native: true },
  { id: 'mistral', runtimes: ['sglang', 'ollama'], native: true },
  { id: 'hermes', runtimes: ['vllm', 'sglang'], native: true },
  { id: 'deepseek', runtimes: ['vllm'], native: true },
  { id: 'glm', runtimes: ['vllm', 'sglang'], native: true },
  { id: 'generic_fallback', runtimes: ['generic'], native: false },
];

const DIAGNOSE: Record<
  RuntimeKind,
  {
    firing: boolean;
    reason: string;
    reason_fa: string;
    fix: string;
    fix_fa: string;
    reduced: boolean;
  }
> = {
  ollama: {
    firing: true,
    reason: 'Ollama tool calling is on by default.',
    reason_fa: 'فراخوانی ابزار در Ollama به‌صورت پیش‌فرض روشن است.',
    fix: 'No change needed. If calls appear as text, update the model and retry the doctor test.',
    fix_fa:
      'تغییری لازم نیست. اگر فراخوانی به‌صورت متن ظاهر شد، مدل را به‌روز کنید و آزمایش را تکرار کنید.',
    reduced: false,
  },
  vllm: {
    firing: false,
    reason: 'This server does not have tool calling enabled.',
    reason_fa: 'این سرور فراخوانی ابزار را فعال نکرده است.',
    fix: 'Start vLLM with --enable-auto-tool-choice --tool-call-parser qwen (or the parser that matches your model family).',
    fix_fa:
      'vLLM را با --enable-auto-tool-choice --tool-call-parser qwen (یا تجزیه‌گر هم‌خوان با خانواده مدل) راه‌اندازی کنید.',
    reduced: false,
  },
  sglang: {
    firing: false,
    reason: 'This server does not have tool calling enabled.',
    reason_fa: 'این سرور فراخوانی ابزار را فعال نکرده است.',
    fix: 'Start SGLang with --tool-call-parser mistral (or the parser that matches your model family).',
    fix_fa:
      'SGLang را با --tool-call-parser mistral (یا تجزیه‌گر هم‌خوان با خانواده مدل) راه‌اندازی کنید.',
    reduced: false,
  },
  llamacpp: {
    firing: false,
    reason: 'llama-server is not emitting structured tool calls.',
    reason_fa: 'llama-server فراخوانی ابزار ساخت‌یافته تولید نمی‌کند.',
    fix: 'Start llama-server with --jinja so templates emit structured tool calls.',
    fix_fa: 'llama-server را با --jinja راه‌اندازی کنید تا قالب‌ها فراخوانی ساخت‌یافته بسازند.',
    reduced: false,
  },
  lmstudio: {
    firing: false,
    reason: 'LM Studio tools are off in the local server settings.',
    reason_fa: 'ابزارهای LM Studio در تنظیمات سرور محلی خاموش هستند.',
    fix: 'Enable structured output / tools in the LM Studio server settings.',
    fix_fa: 'خروجی ساخت‌یافته / ابزارها را در تنظیمات سرور LM Studio روشن کنید.',
    reduced: false,
  },
  generic: {
    firing: true,
    reason: 'Native tools are unavailable. The generic fallback parser is active.',
    reason_fa: 'ابزار بومی در دسترس نیست. تجزیه‌گر پشتیبان عمومی فعال است.',
    fix: 'Expect reduced reliability. Prefer a runtime with native tools when you can.',
    fix_fa: 'قابلیت اطمینان کمتر است. در صورت امکان از زمان‌اجرای دارای ابزار بومی استفاده کنید.',
    reduced: true,
  },
};

let runtimes = seedRuntimes();
let catalog = seedCatalog();
let gateway = seedGateway();

function runtimeById(id: string): RuntimeRecord | undefined {
  return runtimes.find((item) => item.id === id);
}

export function echoCatalog(query = ''): { catalog: CatalogEntry[]; count: number } {
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? catalog.filter(
        (entry) =>
          entry.id.includes(needle) ||
          entry.name.toLowerCase().includes(needle) ||
          entry.notes.toLowerCase().includes(needle),
      )
    : catalog;
  return { catalog: filtered, count: filtered.length };
}

export function echoRuntimes(): { runtimes: RuntimeRecord[]; recommended: RuntimeKind } {
  return { runtimes, recommended: 'ollama' };
}

export function echoHealth(runtimeId: string): {
  runtime_id: string;
  health: RuntimeHealth;
  detected: boolean;
} {
  const runtime = runtimeById(runtimeId);
  if (!runtime) return { runtime_id: runtimeId, health: 'unknown', detected: false };
  return { runtime_id: runtime.id, health: runtime.health, detected: runtime.detected };
}

export function echoModels(runtimeId: string): {
  runtime_id: string;
  models: string[];
  selected_model: string;
} {
  const runtime = runtimeById(runtimeId);
  if (!runtime) return { runtime_id: runtimeId, models: [], selected_model: '' };
  return { runtime_id: runtime.id, models: runtime.models, selected_model: runtime.selected_model };
}

export function echoSelectModel(runtimeId: string, model: string): RuntimeRecord {
  const runtime = runtimeById(runtimeId);
  if (!runtime) throw new Error(`unknown runtime: ${runtimeId}`);
  if (model && runtime.models.includes(model)) runtime.selected_model = model;
  return runtime;
}

export function echoTest(runtimeId: string): ProbeResult {
  const runtime = runtimeById(runtimeId);
  if (!runtime) {
    return {
      runtime_id: 'generic',
      ok: false,
      latency_ms: 4,
      detail: 'Unknown runtime. Try another route.',
      secrets_sent: false,
    };
  }
  const ok = runtime.detected && runtime.health === 'healthy';
  if (ok) runtime.health = 'healthy';
  return {
    runtime_id: runtime.id,
    ok,
    latency_ms: ok ? 6 : 4,
    detail: ok
      ? 'Bounded probe succeeded. No secrets were sent.'
      : 'Runtime did not answer the bounded probe. Try another route.',
    secrets_sent: false,
  };
}

export function echoDiagnose(runtimeId: string): DiagnoseResult {
  const found = runtimeById(runtimeId);
  const id: RuntimeKind = found ? found.id : 'generic';
  const row = DIAGNOSE[id];
  return {
    runtime_id: id,
    firing: row.firing,
    reason: row.reason,
    reason_fa: row.reason_fa,
    fix: row.fix,
    fix_fa: row.fix_fa,
    reduced_reliability: row.reduced,
  };
}

export function echoRoute(): RouteSnapshot {
  return {
    priority: ROUTE_PRIORITY,
    active: 'echo',
    sentence_en:
      'hosted → aval → ollama → byok → echo. The first healthy route wins. Local Ollama is recommended.',
    sentence_fa:
      'hosted → aval → ollama → byok → echo. نخستین مسیر سالم برنده است. Ollama محلی توصیه می‌شود.',
  };
}

export function echoGateway(): GatewayState {
  return {
    ...gateway,
    tools: gateway.tools.map((tool) => ({ ...tool })),
  };
}

export function echoGatewayUpdate(params: {
  enabled?: boolean;
  tool_id?: GatewayToolId;
  tool_enabled?: boolean;
  byok?: boolean;
}): GatewayState {
  if (typeof params.enabled === 'boolean') gateway.enabled = params.enabled;
  if (params.tool_id) {
    const tool = gateway.tools.find((item) => item.id === params.tool_id);
    if (tool) {
      if (typeof params.tool_enabled === 'boolean') tool.enabled = params.tool_enabled;
      if (typeof params.byok === 'boolean') tool.byok = params.byok;
    }
  }
  return echoGateway();
}

export function echoParsers(): { parsers: ParserInfo[] } {
  return { parsers: PARSERS };
}

export function resetEchoProviderHubs(): void {
  runtimes = seedRuntimes();
  catalog = seedCatalog();
  gateway = seedGateway();
}

export { ROUTE_PRIORITY };
