/**
 * Typed wrappers for the `skill.*` RPC family, plus the import/export helpers
 * the Skills manager needs.
 *
 * Validation here mirrors `_validate_skill_safety` in `dream/bridge/methods.py`
 * so a bad paste is caught before it reaches the sidecar; the server still
 * re-checks everything and its verdict wins.
 */

import { zipSync, strToU8 } from 'fflate';

import type { BridgeClient, RequestOptions } from './client';
import type {
  BridgeSkillDetail,
  SkillDeleteResult,
  SkillExportResult,
  SkillGetResult,
  SkillInstallResult,
  SkillListResult,
  SkillToggleResult,
} from './types';

/** Hard cap the backend enforces on a skill file (bytes, UTF-8). */
export const MAX_SKILL_CONTENT_BYTES = 100 * 1024;

/** Extension used for exported skill files. */
export const SKILL_FILE_EXTENSION = '.dream-skill.txt';

/** Modules whose import the backend refuses inside a skill body. */
const DANGEROUS_MODULES = [
  'os',
  'sys',
  'subprocess',
  'shutil',
  'pathlib',
  'socket',
  'ctypes',
  'importlib',
  'pickle',
  'marshal',
  'builtins',
  'code',
  'io',
  'glob',
  'tempfile',
  'platform',
];

const DANGEROUS_IMPORT_RE = new RegExp(
  `^\\s*(?:import\\s+(?:${DANGEROUS_MODULES.join('|')})\\b|from\\s+(?:${DANGEROUS_MODULES.join(
    '|',
  )})\\s+import\\b)`,
  'im',
);
const TRAVERSAL_RE = /\.\.[\\/]|\.[\\/]\.\./;
const ABSOLUTE_PATH_RE = /(?:^|[\s"'])(\/[^\s"']+|[A-Za-z]:[\\/])/;

/** A parsed skill body: the three sections a `.dream-skill.txt` file carries. */
export interface ParsedSkill {
  name: string;
  description: string;
  steps: string[];
}

export type SkillValidationCode =
  'empty' | 'tooLarge' | 'traversal' | 'absolutePath' | 'systemImport' | 'shape';

export interface SkillValidationIssue {
  code: SkillValidationCode;
  sizeKb?: string;
}

/** Outcome of {@link validateSkillContent}. */
export interface SkillValidation {
  ok: boolean;
  /** Blocking problems — install is refused while any are present. */
  errors: string[];
  /** Stable codes let UI layers localize every problem. */
  issues: SkillValidationIssue[];
  /** Parsed sections, present only when `ok`. */
  parsed?: ParsedSkill;
}

/** UTF-8 byte length, matching the server's size check. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

/**
 * Parse a skill file body.
 *
 * Mirrors `dream.skills.parse_skill_text`: `name:` and `description:` are
 * single-line headers and `steps:` introduces a list of `- ` / `1. ` items.
 * Returns `null` when the required sections are missing.
 */
export function parseSkillText(text: string): ParsedSkill | null {
  let name = '';
  let description = '';
  const steps: string[] = [];
  let inSteps = false;

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
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
      const inline = line.slice(6).trim();
      if (inline) steps.push(inline);
    } else if (inSteps) {
      steps.push(
        line
          .replace(/^[-*]\s*/, '')
          .replace(/^\d+[.)]\s*/, '')
          .trim(),
      );
    }
  }

  if (!name || !description || steps.length === 0) return null;
  return { name, description, steps: steps.filter(Boolean) };
}

/** Validate a pasted or imported skill body before installing it. */
export function validateSkillContent(text: string): SkillValidation {
  const errors: string[] = [];
  const issues: SkillValidationIssue[] = [];
  if (!text.trim()) {
    return { ok: false, errors: ['The skill file is empty.'], issues: [{ code: 'empty' }] };
  }
  const bytes = byteLength(text);
  if (bytes > MAX_SKILL_CONTENT_BYTES) {
    const sizeKb = (bytes / 1024).toFixed(1);
    errors.push(`Skill is ${sizeKb} KB — the limit is 100 KB.`);
    issues.push({ code: 'tooLarge', sizeKb });
  }
  if (TRAVERSAL_RE.test(text)) {
    errors.push("Skill must not contain '..' path segments.");
    issues.push({ code: 'traversal' });
  }
  if (ABSOLUTE_PATH_RE.test(text)) {
    errors.push('Skill must not contain absolute file paths.');
    issues.push({ code: 'absolutePath' });
  }
  if (DANGEROUS_IMPORT_RE.test(text)) {
    errors.push('Skill must not contain import statements for system modules.');
    issues.push({ code: 'systemImport' });
  }
  const parsed = parseSkillText(text);
  if (!parsed) {
    errors.push('Skill must define name:, description: and at least one step under steps:.');
    issues.push({ code: 'shape' });
  }
  if (errors.length > 0) return { ok: false, errors, issues };
  return { ok: true, errors: [], issues: [], parsed: parsed ?? undefined };
}

/** Render a skill back to its file representation. */
export function renderSkillText(skill: ParsedSkill): string {
  const lines = [`name: ${skill.name}`, `description: ${skill.description}`, 'steps:'];
  for (const step of skill.steps) lines.push(`- ${step}`);
  return `${lines.join('\n')}\n`;
}

/** Filesystem-safe leaf name for an exported skill. */
export function exportFilename(name: string): string {
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '-')
      .replace(/^-+|-+$/g, '') || 'skill';
  return `${slug}${SKILL_FILE_EXTENSION}`;
}

// --------------------------------------------------------------------------- //
// RPC wrappers
// --------------------------------------------------------------------------- //

/** All installed skills plus any files that failed to parse. */
export function listSkills(
  client: BridgeClient,
  request?: RequestOptions,
): Promise<SkillListResult> {
  return client.call<SkillListResult>('skill.list', {}, request);
}

/** Full detail for one skill, or `null` when it no longer exists. */
export async function getSkill(
  client: BridgeClient,
  skillId: string,
  request?: RequestOptions,
): Promise<BridgeSkillDetail | null> {
  const result = await client.call<SkillGetResult>('skill.get', { skill_id: skillId }, request);
  return result.match;
}

/** Install a skill from a full file body. */
export function installSkill(
  client: BridgeClient,
  content: string,
  options: { overwrite?: boolean; name?: string } = {},
  request?: RequestOptions,
): Promise<SkillInstallResult> {
  const params: Record<string, unknown> = { content, overwrite: options.overwrite ?? false };
  if (options.name) params['name'] = options.name;
  return client.call<SkillInstallResult>('skill.install', params, request);
}

/** Delete a skill file. */
export function deleteSkill(
  client: BridgeClient,
  skillId: string,
  request?: RequestOptions,
): Promise<SkillDeleteResult> {
  return client.call<SkillDeleteResult>('skill.delete', { skill_id: skillId }, request);
}

/** Flip a skill's enabled flag. */
export function setSkillEnabled(
  client: BridgeClient,
  skillId: string,
  enabled: boolean,
  request?: RequestOptions,
): Promise<SkillToggleResult> {
  return client.call<SkillToggleResult>(
    enabled ? 'skill.enable' : 'skill.disable',
    {
      skill_id: skillId,
    },
    request,
  );
}

/** Fetch a skill's file text for download. */
export function exportSkill(
  client: BridgeClient,
  skillId: string,
  request?: RequestOptions,
): Promise<SkillExportResult> {
  return client.call<SkillExportResult>('skill.export', { skill_id: skillId }, request);
}

// --------------------------------------------------------------------------- //
// Browser download helpers
// --------------------------------------------------------------------------- //

/** Trigger a browser/WebView download for `content`. */
export function downloadFile(filename: string, content: BlobPart, mime = 'text/plain'): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Build a ZIP archive of several skill files. */
export function buildSkillZip(entries: Array<{ name: string; content: string }>): Uint8Array {
  const files: Record<string, Uint8Array> = {};
  const used = new Set<string>();
  for (const entry of entries) {
    let leaf = exportFilename(entry.name);
    let counter = 2;
    while (used.has(leaf)) {
      leaf = exportFilename(`${entry.name}-${counter++}`);
    }
    used.add(leaf);
    files[leaf] = strToU8(entry.content);
  }
  return zipSync(files, { level: 6 });
}
