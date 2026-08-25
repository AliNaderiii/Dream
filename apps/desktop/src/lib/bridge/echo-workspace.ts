/**
 * Deterministic echo runtime for the `workspace.*` family.
 *
 * Mirrors the Python handlers so the UI has one code path online and off.
 */

export interface WorkspaceRoot {
  root_id: string;
  name: string;
  path: string;
  imported_in_place: boolean;
  copied: boolean;
  project_id: string | null;
  session_id: string | null;
  created_at: number;
  updated_at: number;
}

export interface WorkspaceEntry {
  path: string;
  name: string;
  size: number;
  type: string;
  mime: string;
  mtime: number;
  is_dir: boolean;
  symlink: boolean;
}

export interface WorkspaceChart {
  kind: string;
  x: string;
  y: string;
  labels: string[];
  values: number[];
}

export interface WorkspacePreview {
  root_id: string;
  path: string;
  name: string;
  type: string;
  size: number;
  executed: boolean;
  truncated: boolean;
  text: string;
  html: string;
  chart: WorkspaceChart | null;
  table: {
    columns: string[];
    rows: string[][];
    row_count: number;
    chart: WorkspaceChart | null;
  } | null;
  warning: string;
}

export interface AgentPlan {
  plan_id: string;
  prompt: string;
  status: string;
  steps: Array<{ index: number; title: string; status: string }>;
  summary: string;
  language: string;
  created_at: number;
  updated_at: number;
  executed: boolean;
  error: string;
}

export interface AgentGoal {
  goal_id: string;
  objective: string;
  criteria: string[];
  status: string;
  results: Array<{ criterion: string; met: boolean; reason: string }>;
  unmet: string[];
  report: string;
}

export interface LiveSubagent {
  agent_id: string;
  name: string;
  status: string;
  latest_action: string;
  progress: number;
  live: boolean;
}

const BASE = Date.UTC(2026, 7, 25, 9, 0, 0) / 1000;

const SEED_CSV = `region,revenue
North,120
South,80
East,60`;

const SEED_CHART: WorkspaceChart = {
  kind: 'bar',
  x: 'region',
  y: 'revenue',
  labels: ['North', 'South', 'East'],
  values: [120, 80, 60],
};

const SEED_ROOT: WorkspaceRoot = {
  root_id: 'wsr_echo_demo',
  name: 'Demo workspace',
  path: '/workspace/demo',
  imported_in_place: true,
  copied: false,
  project_id: 'prj_echo_demo',
  session_id: null,
  created_at: BASE,
  updated_at: BASE,
};

const SEED_FILES: WorkspaceEntry[] = [
  {
    path: 'README.md',
    name: 'README.md',
    size: 32,
    type: 'markdown',
    mime: 'text/markdown',
    mtime: BASE,
    is_dir: false,
    symlink: false,
  },
  {
    path: 'sales.csv',
    name: 'sales.csv',
    size: 48,
    type: 'csv',
    mime: 'text/csv',
    mtime: BASE,
    is_dir: false,
    symlink: false,
  },
  {
    path: 'notes',
    name: 'notes',
    size: 0,
    type: 'directory',
    mime: 'inode/directory',
    mtime: BASE,
    is_dir: true,
    symlink: false,
  },
];

const NOTES_FILES: WorkspaceEntry[] = [
  {
    path: 'notes/todo.md',
    name: 'todo.md',
    size: 22,
    type: 'markdown',
    mime: 'text/markdown',
    mtime: BASE,
    is_dir: false,
    symlink: false,
  },
];

const SAFE_SHELL = new Set(['pwd', 'echo', 'date', 'whoami', 'true', 'false']);
const GUARDED_SHELL = new Set(['ls', 'cat', 'head', 'tail', 'wc', 'stat', 'file']);
const DANGEROUS_SHELL =
  /\b(rm|curl|wget|ssh|sudo|chmod|chown|mkfs|dd|python|perl|node|npm|nc|ncat|bash|sh|exec|source|eval)\b|[;&|`$()<>]|\/etc\/|\/proc\//;

function classifyEchoCommand(command: string): string {
  const stripped = command.trim();
  if (!stripped || stripped.length > 500)
    throw new Error('command must be a short non-empty string');
  if (DANGEROUS_SHELL.test(stripped)) return 'dangerous';
  const parts = stripped.split(/\s+/).filter(Boolean);
  const name = (parts[0] ?? '').split(/[/\\]/).pop()?.toLowerCase() ?? '';
  if (SAFE_SHELL.has(name) && parts.length <= 4) return 'safe';
  if (GUARDED_SHELL.has(name) && parts.length <= 6) return 'guarded';
  return 'dangerous';
}

function echoPathEscapes(command: string): boolean {
  const parts = command.trim().split(/\s+/).slice(1);
  return parts.some((arg) => {
    if (arg.startsWith('-') && !arg.includes('/') && !arg.includes('..')) return false;
    return arg === '..' || arg.includes('..') || arg.startsWith('/') || /^[A-Za-z]:[\\/]/.test(arg);
  });
}

function echoFileNames(): Set<string> {
  const names = new Set<string>();
  for (const entries of files.values()) {
    for (const entry of entries) names.add(entry.name.toLowerCase());
  }
  for (const entry of NOTES_FILES) names.add(entry.name.toLowerCase());
  return names;
}

function evaluateEchoCriterion(
  criterion: string,
  names: Set<string>,
): { met: boolean; reason: string } {
  const lower = criterion.toLowerCase();
  if (/network|live market|production deploy|exfiltrat|ignore previous/i.test(criterion)) {
    return {
      met: false,
      reason: `could not meet '${criterion}': requires capabilities that are off`,
    };
  }
  if (
    /has_more/.test(lower) ||
    /list(_|\s*)cap/.test(lower) ||
    (lower.includes('bounded') && lower.includes('list')) ||
    (lower.includes('listing') && (lower.includes('cap') || lower.includes('bound')))
  ) {
    return { met: true, reason: 'listing respected LIST_CAP' };
  }
  const words: string[] = lower.match(/[a-z0-9._-]+/g) ?? [];
  for (const name of names) {
    if (lower.includes(name)) {
      return { met: true, reason: 'found under a registered workspace root' };
    }
    const stem = name.includes('.') ? name.slice(0, name.lastIndexOf('.')) : name;
    if (stem.length >= 3 && words.includes(stem)) {
      return { met: true, reason: 'found under a registered workspace root' };
    }
  }
  return {
    met: false,
    reason: `could not meet '${criterion}': not verifiable from the local workspace`,
  };
}

const roots = new Map<string, WorkspaceRoot>([[SEED_ROOT.root_id, { ...SEED_ROOT }]]);
const files = new Map<string, WorkspaceEntry[]>([
  [SEED_ROOT.root_id, SEED_FILES.map((row) => ({ ...row }))],
]);
const plans = new Map<string, AgentPlan>();
const goals = new Map<string, AgentGoal>();
const subagents = new Map<string, LiveSubagent>();
const shellPending = new Map<
  string,
  { command: string; risk: string; executed: boolean; cwd: string }
>();
let counter = 1;

function now(): number {
  return Date.now() / 1000;
}

function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}_echo_${counter.toString(16).padStart(4, '0')}`;
}

function requireRoot(rootId: string): WorkspaceRoot {
  const root = roots.get(rootId);
  if (!root) throw new Error(`no workspace root with id ${rootId}`);
  return root;
}

export function echoRootsList(): { roots: WorkspaceRoot[]; count: number } {
  const list = [...roots.values()].sort((a, b) => b.updated_at - a.updated_at);
  return { roots: list, count: list.length };
}

export function echoImportFolder(
  folder: string,
  name?: string,
): {
  root: WorkspaceRoot;
  project: { project_id: string; name: string; folder: string; copied: boolean };
  copied: boolean;
  imported_in_place: boolean;
  listing: { path: string; entries: WorkspaceEntry[]; count: number; has_more: boolean };
} {
  if (!folder.trim()) throw new Error('folder must be a non-empty string');
  if (folder.includes('..')) throw new Error('parent-directory traversal is refused');
  const root: WorkspaceRoot = {
    root_id: nextId('wsr'),
    name: name?.trim() || 'Imported folder',
    path: folder,
    imported_in_place: true,
    copied: false,
    project_id: nextId('prj'),
    session_id: null,
    created_at: now(),
    updated_at: now(),
  };
  roots.set(root.root_id, root);
  files.set(
    root.root_id,
    SEED_FILES.map((row) => ({ ...row })),
  );
  return {
    root,
    project: {
      project_id: root.project_id ?? nextId('prj'),
      name: root.name,
      folder,
      copied: false,
    },
    copied: false,
    imported_in_place: true,
    listing: { path: '', entries: files.get(root.root_id) ?? [], count: 3, has_more: false },
  };
}

export function echoUnregister(rootId: string): { deleted: boolean; root_id: string } {
  requireRoot(rootId);
  roots.delete(rootId);
  files.delete(rootId);
  return { deleted: true, root_id: rootId };
}

export function echoFilesList(
  rootId: string,
  rel = '',
): {
  root_id: string;
  path: string;
  entries: WorkspaceEntry[];
  count: number;
  cursor: number;
  next_cursor: null;
  has_more: boolean;
  truncated: boolean;
} {
  requireRoot(rootId);
  if (rel.includes('..')) throw new Error('parent-directory traversal is refused');
  const normalized = rel
    .replace(/\\/g, '/')
    .replace(/^\.\/+/, '')
    .replace(/^\/+|\/+$/g, '');
  if (normalized === 'notes') {
    const nested = NOTES_FILES.map((row) => ({ ...row }));
    return {
      root_id: rootId,
      path: 'notes',
      entries: nested,
      count: nested.length,
      cursor: 0,
      next_cursor: null,
      has_more: false,
      truncated: false,
    };
  }
  if (normalized) {
    return {
      root_id: rootId,
      path: normalized,
      entries: [],
      count: 0,
      cursor: 0,
      next_cursor: null,
      has_more: false,
      truncated: false,
    };
  }
  const entries = files.get(rootId) ?? [];
  return {
    root_id: rootId,
    path: rel,
    entries,
    count: entries.length,
    cursor: 0,
    next_cursor: null,
    has_more: false,
    truncated: false,
  };
}

export function echoFilesPreview(rootId: string, rel: string): WorkspacePreview {
  requireRoot(rootId);
  if (rel.includes('..')) throw new Error('parent-directory traversal is refused');
  if (rel.endsWith('.csv')) {
    return {
      root_id: rootId,
      path: rel,
      name: 'sales.csv',
      type: 'csv',
      size: SEED_CSV.length,
      executed: false,
      truncated: false,
      text: SEED_CSV,
      html: '',
      chart: SEED_CHART,
      table: {
        columns: ['region', 'revenue'],
        rows: [
          ['North', '120'],
          ['South', '80'],
          ['East', '60'],
        ],
        row_count: 3,
        chart: SEED_CHART,
      },
      warning: '',
    };
  }
  return {
    root_id: rootId,
    path: rel,
    name: rel.split('/').pop() ?? rel,
    type: 'markdown',
    size: 32,
    executed: false,
    truncated: false,
    text: '# Demo workspace\n\nImported in place — never copied.',
    html: '',
    chart: null,
    table: null,
    warning: '',
  };
}

export function echoFilesRead(rootId: string, rel: string) {
  const preview = echoFilesPreview(rootId, rel);
  return {
    root_id: rootId,
    path: preview.path,
    type: preview.type,
    text: preview.text,
    truncated: preview.truncated,
  };
}

export function echoProjectSettings(projectId: string, updates?: Record<string, string>) {
  return {
    project_id: projectId,
    settings: {
      default_mode: updates?.default_mode ?? 'chat',
      language: updates?.language ?? 'en',
    },
    copied: false,
  };
}

export function echoMoveSession(projectId: string, sessionId: string) {
  return { project_id: projectId, session_ids: [sessionId], copied: false };
}

export function echoPlan(prompt: string): AgentPlan {
  if (!prompt.trim()) throw new Error('prompt must be a non-empty string');
  const plan: AgentPlan = {
    plan_id: nextId('plan'),
    prompt,
    status: 'pending_approval',
    steps: [
      {
        index: 1,
        title: 'Gather the relevant workspace files and conversations',
        status: 'pending',
      },
      { index: 2, title: 'Draft the change or analysis without applying it', status: 'pending' },
      { index: 3, title: 'Apply the approved steps and record provenance', status: 'pending' },
    ],
    summary: prompt.slice(0, 240),
    language: /[\u0600-\u06ff]/.test(prompt) ? 'fa' : 'en',
    created_at: now(),
    updated_at: now(),
    executed: false,
    error: '',
  };
  plans.set(plan.plan_id, plan);
  subagents.set(plan.plan_id, {
    agent_id: plan.plan_id,
    name: 'planner',
    status: 'pending_approval',
    latest_action: 'drafted plan',
    progress: 0.2,
    live: true,
  });
  return { ...plan, steps: plan.steps.map((step) => ({ ...step })) };
}

export function echoContinue(planId: string): AgentPlan {
  const plan = plans.get(planId);
  if (!plan) throw new Error(`no plan with id ${planId}`);
  plan.status = 'complete';
  plan.executed = true;
  plan.steps = plan.steps.map((step) => ({ ...step, status: 'done' }));
  plan.updated_at = now();
  subagents.set(planId, {
    agent_id: planId,
    name: 'planner',
    status: 'complete',
    latest_action: 'executed plan',
    progress: 1,
    live: true,
  });
  return { ...plan, steps: plan.steps.map((step) => ({ ...step })) };
}

export function echoGoal(objective: string, criteria: string[]): AgentGoal {
  if (!objective.trim()) throw new Error('objective must be a non-empty string');
  if (!criteria.length) throw new Error('criteria must be a non-empty list of strings');
  const names = echoFileNames();
  const results = criteria.map((criterion) => {
    const checked = evaluateEchoCriterion(criterion, names);
    return { criterion, met: checked.met, reason: checked.reason };
  });
  const unmet = results.filter((row) => !row.met).map((row) => row.criterion);
  const goal: AgentGoal = {
    goal_id: nextId('goal'),
    objective,
    criteria,
    status: unmet.length ? 'unable' : 'complete',
    results,
    unmet,
    report: unmet.length
      ? `could not meet ${unmet.join('; ')}`
      : 'All acceptance criteria were met.',
  };
  goals.set(goal.goal_id, goal);
  subagents.set(goal.goal_id, {
    agent_id: goal.goal_id,
    name: 'goal',
    status: goal.status,
    latest_action: goal.report,
    progress: unmet.length ? 0.6 : 1,
    live: true,
  });
  return {
    ...goal,
    criteria: [...goal.criteria],
    unmet: [...goal.unmet],
    results: goal.results.map((row) => ({ ...row })),
  };
}

export function echoStop() {
  for (const plan of plans.values()) {
    if (plan.status === 'pending_approval' || plan.status === 'running') {
      plan.status = 'cancelled';
      plan.updated_at = now();
    }
  }
  for (const agent of subagents.values()) {
    if (agent.status === 'running' || agent.status === 'pending_approval') {
      agent.status = 'cancelled';
      agent.latest_action = 'cancelled';
    }
  }
  return {
    stopped: true,
    live: true,
    plans: [...plans.values()],
    goals: [...goals.values()],
    subagents: [...subagents.values()],
  };
}

export function echoStatus() {
  const planRows = [...plans.values()];
  const running = planRows.some(
    (item) => item.status === 'running' || item.status === 'pending_approval',
  );
  const cancelled = planRows.some((item) => item.status === 'cancelled');
  return {
    running,
    cancelled: cancelled && !running,
    live: true,
    plans: planRows,
    goals: [...goals.values()],
    subagents: [...subagents.values()],
  };
}

export function echoSubagentsLive() {
  if (subagents.size === 0) {
    subagents.set('sub_echo_writer', {
      agent_id: 'sub_echo_writer',
      name: 'writer',
      status: 'running',
      latest_action: 'drafting section 2',
      progress: 0.45,
      live: true,
    });
  }
  return { subagents: [...subagents.values()], count: subagents.size, live: true };
}

export function echoRefsParse(text: string) {
  const files = [...text.matchAll(/@([^\s@#/!]{1,240})/g)].map((match) => match[1]);
  const conversations = [...text.matchAll(/#([A-Za-z0-9_-]{1,80})/g)].map((match) => match[1]);
  const commands = [...text.matchAll(/(?:^|\s)\/([A-Za-z0-9_\u0600-\u06ff-]{1,40})/g)].map(
    (match) => match[1],
  );
  const shell = [...text.matchAll(/(?:^|\s)!([^\n]{1,500})/g)]
    .map((match) => match[1].trim())
    .filter(Boolean);
  return { files, conversations, commands, shell };
}

export function echoCommands(query = '') {
  const all = [
    { name: 'plan', title: '/plan', summary: 'Plan first, execute only after continue' },
    { name: 'goal', title: '/goal', summary: 'Capture an objective and acceptance criteria' },
    { name: 'stop', title: '/stop', summary: 'Cancel the running turn (live server state)' },
    { name: 'status', title: '/status', summary: 'Live subagent and mode status' },
  ];
  const needle = query.trim().replace(/^\//, '').toLowerCase();
  const commands = needle
    ? all.filter(
        (item) => item.name.includes(needle) || item.summary.toLowerCase().includes(needle),
      )
    : all;
  return { commands, count: commands.length };
}

export function echoShellPropose(command: string, cwd?: string) {
  if (!command.trim()) throw new Error('command must be a short non-empty string');
  const risk = classifyEchoCommand(command);
  const approvalId = nextId('sh');
  shellPending.set(approvalId, { command, risk, executed: false, cwd: cwd?.trim() ?? '' });
  return {
    approval_id: approvalId,
    command,
    risk,
    network: false,
    requires_approval: risk !== 'safe',
    executed: false,
  };
}

export function echoShellExecute(approvalId: string, approved = false) {
  const pending = shellPending.get(approvalId);
  if (!pending) throw new Error(`no shell proposal with id ${approvalId}`);
  if (pending.risk !== 'safe' && !approved)
    throw new Error('this command requires explicit approval');
  if (pending.risk === 'dangerous') {
    return {
      approval_id: approvalId,
      executed: false,
      returncode: -1,
      stdout: '',
      stderr: 'dangerous shell commands are refused',
      timed_out: false,
      network: false,
      risk: pending.risk,
    };
  }
  if (pending.risk === 'guarded') {
    const cwd = pending.cwd.trim();
    if (!cwd) throw new Error('cwd must be a registered workspace root');
    const registered = [...roots.values()].some((root) => root.path === cwd);
    if (!registered) throw new Error('cwd must be a registered workspace root');
    if (echoPathEscapes(pending.command)) throw new Error('parent-directory traversal is refused');
  }
  pending.executed = true;
  return {
    approval_id: approvalId,
    executed: true,
    returncode: 0,
    stdout: 'echo: command not run against a live host',
    stderr: '',
    timed_out: false,
    network: false,
    risk: pending.risk,
  };
}

export function echoRefsFile(rootId: string, rel: string) {
  const preview = echoFilesPreview(rootId, rel);
  return {
    path: preview.path,
    type: preview.type,
    summary: preview.text.slice(0, 400),
    chart: preview.chart,
  };
}

export function echoRefsConversation(sessionId: string) {
  if (!sessionId.trim()) throw new Error('session_id must be a non-empty string');
  return { session_id: sessionId, reference: `#${sessionId}`, kind: 'conversation' };
}

export function getSeedRootId(): string {
  return SEED_ROOT.root_id;
}

export function resetEchoWorkspace(): void {
  roots.clear();
  files.clear();
  plans.clear();
  goals.clear();
  subagents.clear();
  shellPending.clear();
  counter = 1;
  roots.set(SEED_ROOT.root_id, { ...SEED_ROOT });
  files.set(
    SEED_ROOT.root_id,
    SEED_FILES.map((row) => ({ ...row })),
  );
}
