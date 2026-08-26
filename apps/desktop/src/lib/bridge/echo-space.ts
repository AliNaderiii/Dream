/** Deterministic echo runtime for the `space.*` family. */

export type SpaceCeiling = 'safe' | 'guarded';
export type DraftStatus = 'APPROVAL_PENDING' | 'APPROVED' | 'DENIED';

export interface SpaceRole {
  role_id: string;
  name_en: string;
  name_fa: string;
  job_en: string;
  job_fa: string;
  tools: string[];
  risk_ceiling: SpaceCeiling;
  effective_ceiling?: SpaceCeiling;
}

export interface SpaceRecord {
  space_id: string;
  name: string;
  language: string;
  ceiling: SpaceCeiling;
  archived: boolean;
  root_id: string | null;
  folder: string | null;
  copied: boolean;
  imported_in_place: boolean;
  instruction: { source: string; text: string; bytes: number; findings: string[] } | null;
  created_at: number;
  updated_at: number;
}

export interface SpaceDraft {
  draft_id: string;
  space_id: string;
  rule: string;
  status: DraftStatus;
  cron: string;
  parse_error: string;
  shell: Array<{ command: string; risk: string }>;
  dangerous: boolean;
  fired: boolean;
  spawned: boolean;
  created_at: number;
  updated_at: number;
}

const ROLES: SpaceRole[] = [
  {
    role_id: 'secretary',
    name_en: 'Secretary',
    name_fa: 'منشی',
    job_en: 'Keep notes, recall profile facts, and answer scheduling questions.',
    job_fa: 'یادداشت، بازیابی نمایه، و پرسش‌های زمان‌بندی.',
    tools: ['get_datetime', 'remember_fact', 'list_notes'],
    risk_ceiling: 'safe',
  },
  {
    role_id: 'research',
    name_en: 'Research',
    name_fa: 'پژوهش',
    job_en: 'Plan and summarise local research; no live web unless the owner enabled network.',
    job_fa: 'برنامه و خلاصهٔ پژوهش محلی؛ وب زنده فقط با اجازهٔ شبکه.',
    tools: ['get_datetime', 'read_note', 'list_notes'],
    risk_ceiling: 'guarded',
  },
  {
    role_id: 'data',
    name_en: 'Data',
    name_fa: 'داده',
    job_en: 'Describe local tables honestly. Never evaluate model-authored code.',
    job_fa: 'توصیف صادقانهٔ جدول‌های محلی. هرگز کد مدل را اجرا نکن.',
    tools: ['list_notes', 'read_note', 'calculate'],
    risk_ceiling: 'guarded',
  },
  {
    role_id: 'desk',
    name_en: 'Desk',
    name_fa: 'میزکار',
    job_en: 'Read files that are already attached to this Space. Never copy folders.',
    job_fa: 'خواندن فایل‌های پیوست همین فضا. هرگز پوشه را کپی نکن.',
    tools: ['list_notes', 'read_note'],
    risk_ceiling: 'safe',
  },
  {
    role_id: 'security',
    name_en: 'Security',
    name_fa: 'امنیت',
    job_en: 'Audit drafts and refuse dangerous shell. Read-only.',
    job_fa: 'ممیزی پیشنویس‌ها و رد پوستهٔ خطرناک. فقط خواندنی.',
    tools: ['get_datetime'],
    risk_ceiling: 'safe',
  },
];

const SEED_ID = 'spc_echo_demo';

function seedRecord(): SpaceRecord {
  const now = Date.UTC(2026, 7, 26, 12, 0, 0) / 1000;
  return {
    space_id: SEED_ID,
    name: 'Studio',
    language: 'en',
    ceiling: 'guarded',
    archived: false,
    root_id: 'wsr_echo_demo',
    folder: '/workspace/demo',
    copied: false,
    imported_in_place: true,
    instruction: {
      source: 'pasted',
      text: 'Outcome: a weekly brief.\nSources: local notes only.\nConstraints: never send mail.\nDeliverable: five bullets.\nReview point: owner approves before anything leaves the machine.',
      bytes: 180,
      findings: [],
    },
    created_at: now,
    updated_at: now,
  };
}

const spaces = new Map<string, SpaceRecord>([[SEED_ID, seedRecord()]]);
const drafts = new Map<string, SpaceDraft>();
let counter = 1;

function stamp(): number {
  return Date.now() / 1000;
}

function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}_echo_${counter.toString(16).padStart(4, '0')}`;
}

function requireSpace(spaceId: string): SpaceRecord {
  const record = spaces.get(spaceId);
  if (!record || record.archived) throw new Error(`no space with id ${spaceId}`);
  return record;
}

export function echoSpaceCatalog(): { roles: SpaceRole[]; count: number } {
  return { roles: ROLES.map((role) => ({ ...role, tools: [...role.tools] })), count: ROLES.length };
}

export function echoSpaceCreate(name: string, language = 'en', ceiling: SpaceCeiling = 'guarded') {
  if (!name.trim()) throw new Error('name must be a non-empty string of at most 120 characters');
  if (ceiling === ('dangerous' as SpaceCeiling)) {
    throw new Error('space risk ceiling cannot be dangerous');
  }
  const now = stamp();
  const record: SpaceRecord = {
    space_id: nextId('spc'),
    name: name.trim(),
    language: language === 'fa' ? 'fa' : 'en',
    ceiling,
    archived: false,
    root_id: null,
    folder: null,
    copied: false,
    imported_in_place: false,
    instruction: null,
    created_at: now,
    updated_at: now,
  };
  spaces.set(record.space_id, record);
  return { ...record };
}

export function echoSpaceList() {
  const rows = [...spaces.values()].filter((row) => !row.archived);
  return { spaces: rows.map((row) => ({ ...row })), count: rows.length };
}

export function echoSpaceGet(spaceId: string) {
  const record = requireSpace(spaceId);
  return {
    ...record,
    drafts: [...drafts.values()].filter((row) => row.space_id === spaceId),
    roles: ROLES.map((role) => ({
      ...role,
      tools: [...role.tools],
      effective_ceiling:
        role.risk_ceiling === 'guarded' && record.ceiling === 'safe' ? 'safe' : role.risk_ceiling,
    })),
  };
}

export function echoSpaceArchive(spaceId: string) {
  const record = requireSpace(spaceId);
  record.archived = true;
  record.updated_at = stamp();
  return { archived: true, space_id: spaceId };
}

export function echoSpaceAttach(spaceId: string, folder: string) {
  const record = requireSpace(spaceId);
  if (!folder.trim()) throw new Error('folder must be a non-empty string');
  if (folder.includes('..')) throw new Error('parent-directory traversal is refused');
  record.root_id = nextId('wsr');
  record.folder = folder;
  record.copied = false;
  record.imported_in_place = true;
  record.updated_at = stamp();
  return {
    space: { ...record },
    root: { root_id: record.root_id, path: folder, copied: false },
    copied: false,
    imported_in_place: true,
  };
}

export function echoSpaceSetInstruction(spaceId: string, text?: string, path?: string) {
  const record = requireSpace(spaceId);
  const body = (text ?? '').trim();
  const source = path?.trim() ?? 'pasted';
  if (source.startsWith('http://') || source.startsWith('https://')) {
    throw new Error('web instruction sources are refused while network tools are off');
  }
  if (
    /ignore\s+previous\s+instructions/i.test(body) ||
    /ignore\s+previous\s+instructions/i.test(source)
  ) {
    throw new Error('instruction doc looks like a prompt injection and was quarantined');
  }
  if (!body) throw new Error('instruction text must be non-empty');
  record.instruction = { source, text: body, bytes: body.length, findings: [] };
  record.updated_at = stamp();
  return { space_id: spaceId, instruction: { ...record.instruction } };
}

export function echoSpaceAsk(spaceId: string, roleId: string, question: string) {
  const record = requireSpace(spaceId);
  const role = ROLES.find((item) => item.role_id === roleId);
  if (!role) throw new Error(`unknown role ${roleId}`);
  if (!question.trim())
    throw new Error('question must be a non-empty string of at most 4000 characters');
  if (!record.instruction) throw new Error('this space has no instruction doc yet');
  const ceiling =
    role.risk_ceiling === 'guarded' && record.ceiling === 'safe' ? 'safe' : role.risk_ceiling;
  return {
    space_id: spaceId,
    role: { ...role, tools: [...role.tools], effective_ceiling: ceiling },
    question,
    hosted: false,
    tools: [...role.tools],
    answer: `${role.name_en} — ${role.job_en}\nEffective risk ceiling: ${ceiling}. This is a local briefing; no hosted model was called.\nQuestion: ${question}\nFrom the instruction doc:\n${record.instruction.text}`,
  };
}

export function echoSpacePropose(spaceId: string, rule: string): SpaceDraft {
  requireSpace(spaceId);
  if (!rule.trim()) throw new Error('rule must be a non-empty string of at most 2000 characters');
  const dangerous = /!\s*(rm|curl|wget|sudo|bash|sh)\b/i.test(rule);
  const now = stamp();
  const draft: SpaceDraft = {
    draft_id: nextId('dft'),
    space_id: spaceId,
    rule,
    status: 'APPROVAL_PENDING',
    cron: /9\s*AM|۹\s*صبح/i.test(rule) ? '0 9 * * *' : '',
    parse_error: '',
    shell: dangerous ? [{ command: 'rm', risk: 'dangerous' }] : [],
    dangerous,
    fired: false,
    spawned: false,
    created_at: now,
    updated_at: now,
  };
  drafts.set(draft.draft_id, draft);
  return { ...draft, shell: draft.shell.map((row) => ({ ...row })) };
}

export function echoSpaceListDrafts(spaceId: string) {
  requireSpace(spaceId);
  const rows = [...drafts.values()].filter((row) => row.space_id === spaceId);
  return { drafts: rows.map((row) => ({ ...row })), count: rows.length };
}

export function echoSpaceApprove(draftId: string) {
  const draft = drafts.get(draftId);
  if (!draft) throw new Error(`no draft with id ${draftId}`);
  if (draft.status === 'DENIED') throw new Error('a denied draft stays idle');
  draft.status = 'APPROVED';
  draft.updated_at = stamp();
  return { ...draft };
}

export function echoSpaceDeny(draftId: string) {
  const draft = drafts.get(draftId);
  if (!draft) throw new Error(`no draft with id ${draftId}`);
  draft.status = 'DENIED';
  draft.updated_at = stamp();
  return { ...draft };
}

export function echoSpaceRun(draftId: string, approved = false) {
  const draft = drafts.get(draftId);
  if (!draft) throw new Error(`no draft with id ${draftId}`);
  if (draft.status !== 'APPROVED') {
    throw new Error('draft is not approved; nothing was scheduled or executed');
  }
  if (!approved) throw new Error('missing approver — refuse');
  if (draft.dangerous) {
    return {
      draft_id: draftId,
      executed: false,
      spawned: false,
      fired: false,
      status: draft.status,
      reason: 'dangerous shell commands are refused',
    };
  }
  return {
    draft_id: draftId,
    executed: false,
    spawned: false,
    fired: false,
    status: draft.status,
    cron: draft.cron,
    reason: 'approved draft stored; live scheduler wiring is a documented residual',
  };
}

export function resetEchoSpace(): void {
  spaces.clear();
  drafts.clear();
  counter = 1;
}
