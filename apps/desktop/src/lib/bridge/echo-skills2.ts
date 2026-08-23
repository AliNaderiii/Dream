/**
 * Echo runtime for the Stage F `skills.*` v2 families — the browser/test
 * stand-in for the kernel's ledger, proposal inbox, `/learn` classifier and
 * reference listings.
 *
 * Wire discipline mirrors `dream.bridge.methods`:
 *
 * - version and use rows are plain JSON objects in the kernel's exact key
 *   order (`asdict` on the Python side);
 * - proposals list oldest-first; applying an unknown or resolved id is an
 *   invalid-params refusal; discarding a never-pending id answers
 *   `{discarded: false}` without an error;
 * - `/learn` classification is offline-first: a URL source while network
 *   tools are off is refused up front with the bilingual kernel message
 *   (Persian fragment اینترنتی + `network tools`), and an empty conversation
 *   refuses rather than inventing a source;
 * - references belong to v2 skill folders; legacy skills answer `[]`.
 */

import { BridgeRpcError } from './errors';
import type { RpcParams } from './types';

/** Wire shape of one version row (mirrors `asdict(SkillVersion)`). */
export interface EchoSkillVersion {
  name: string;
  version: number;
  content: string;
  kind: string;
  created_at: number;
}

/** Wire shape of one use row (mirrors `asdict(SkillUse)`). */
export interface EchoSkillUse {
  name: string;
  invoked_at: number;
  outcome: string;
  duration_ms: number;
  source: string;
}

/** Wire shape of one pending proposal (mirrors `asdict(SkillProposal)`). */
export interface EchoSkillProposal {
  proposal_id: string;
  name: string;
  description: string;
  body: string;
  action: string;
  created_at: number;
}

/** One classified `/learn` source (mirrors the bridge payload). */
export interface EchoLearnSource {
  kind: 'path' | 'corpus' | 'conversation' | 'notes' | 'url';
  topic: string;
  text: string;
  existing: string | null;
}

function invalid(message: string, data?: Record<string, unknown>): BridgeRpcError {
  return new BridgeRpcError({ code: -32602, message, ...(data ? { data } : {}) });
}

/** Bilingual offline-URL refusal; identical law to `dream.skills.learn`. */
function urlOffRefusal(): BridgeRpcError {
  return invalid(
    // Gloss: «یادگیری از نشانی اینترنتی فقط وقتی مجاز است که ابزار شبکه روشن
    // باشد و دریافت تایید شود. الان شبکه خاموش است.»
    '\u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u0627\u0632 \u0646\u0634\u0627\u0646\u06cc ' +
      '\u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc \u0641\u0642\u0637 \u0648\u0642\u062a\u06cc ' +
      '\u0645\u062c\u0627\u0632 \u0627\u0633\u062a \u06a9\u0647 \u0627\u0628\u0632\u0627\u0631 ' +
      '\u0634\u0628\u06a9\u0647 \u0631\u0648\u0634\u0646 \u0628\u0627\u0634\u062f \u0648 \u062f\u0631\u06cc\u0627' +
      '\u0641\u062a \u062a\u0627\u06cc\u06cc\u062f \u0634\u0648\u062f. \u0627\u0644\u0627\u0646 \u0634\u0628' +
      '\u06a9\u0647 \u062e\u0627\u0645\u0648\u0634 \u0627\u0633\u062a\u061b \u0627\u0632 \u0645\u0633\u06cc\u0631 ' +
      '\u0645\u062d\u0644\u06cc\u060c \u06af\u0641\u062a\u06af\u0648 \u06cc\u0627 \u06cc\u0627\u062f\u062f\u0627' +
      '\u0634\u062a \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646. ' +
      'URL learning is allowed only when network tools are enabled and the fetch is ' +
      'approved. Network tools are off; use a local path, the conversation, or pasted notes.',
    { kind: 'url' },
  );
}

/** Bilingual empty-source refusal. */
function emptySourceRefusal(kind: string): BridgeRpcError {
  return invalid(
    // Gloss: «منبع یادگیری خالی است یا خوانده نشد.»
    '\u0645\u0646\u0628\u0639 \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u062e\u0627\u0644\u06cc ' +
      '\u0627\u0633\u062a \u06cc\u0627 \u062e\u0648\u0627\u0646\u062f\u0647 \u0646\u0634\u062f. ' +
      'The learn source is empty or could not be read.',
    { kind },
  );
}

function slugify(text: string, fallback: string): string {
  const slug = text
    .toLowerCase()
    .split(/\s+/)
    .slice(0, 4)
    .join('-')
    .replace(/[^a-z0-9-]+/g, '');
  return slug || fallback;
}

const WEEKLY_V1 =
  '## Purpose\n\nSummarise the week from the session log.\n\n## Instructions\n\n1. Collect sessions\n2. Group by project\n';
const WEEKLY_V2 =
  '## Purpose\n\nSummarise the week from the session log.\n\n## Instructions\n\n1. Collect sessions from the past 7 days\n2. Group them by project\n3. Write a summary\n';

const NOW = 1_780_000_000;

/**
 * Lazily-created echo runtime for the skills v2 bridge families. Tests reach
 * the knobs (`setNetworkEnabled`, seeds) through the owning transport.
 */
export class EchoSkills2Runtime {
  private versions = new Map<string, EchoSkillVersion[]>();
  private referenceFiles = new Map<string, Array<{ name: string; bytes: number }>>();
  private uses: EchoSkillUse[] = [];
  private proposals = new Map<string, EchoSkillProposal>();
  private networkEnabled = false;
  private proposalSeq = 0;

  constructor() {
    this.versions.set('weekly-report', [
      {
        name: 'weekly-report',
        version: 1,
        content: WEEKLY_V1,
        kind: 'skill_md',
        created_at: NOW - 86_400,
      },
      {
        name: 'weekly-report',
        version: 2,
        content: WEEKLY_V2,
        kind: 'skill_md',
        created_at: NOW - 3_600,
      },
    ]);
    this.versions.set('triage-inbox', [
      {
        name: 'triage-inbox',
        version: 1,
        content: '## Purpose\n\nSort incoming notes.\n',
        kind: 'skill_md',
        created_at: NOW - 172_800,
      },
    ]);
    this.referenceFiles.set('weekly-report', [
      { name: 'glossary', bytes: 412 },
      { name: 'seven-day-window', bytes: 256 },
    ]);
    this.uses = [
      {
        name: 'weekly-report',
        invoked_at: NOW - 500,
        outcome: 'ok',
        duration_ms: 120,
        source: 'slash',
      },
      {
        name: 'weekly-report',
        invoked_at: NOW - 400,
        outcome: 'ok',
        duration_ms: 180,
        source: 'slash',
      },
      {
        name: 'weekly-report',
        invoked_at: NOW - 300,
        outcome: 'timeout',
        duration_ms: 4_000,
        source: 'use_skill',
      },
      {
        name: 'triage-inbox',
        invoked_at: NOW - 200,
        outcome: 'ok',
        duration_ms: 90,
        source: 'slash',
      },
    ];
    this.proposals.set('prop-1', {
      proposal_id: 'prop-1',
      name: 'weekly-report',
      description: 'Fold the 7-day window rule into the weekly summary.',
      body: WEEKLY_V2,
      action: 'improve',
      created_at: NOW - 900,
    });
    this.proposalSeq = 1;
  }

  /** Test/embed hook: flip the network tools switch the classifier consults. */
  setNetworkEnabled(enabled: boolean): void {
    this.networkEnabled = enabled;
  }

  handles(method: string): boolean {
    return method.startsWith('skills.');
  }

  handle(method: string, params: RpcParams): unknown {
    switch (method) {
      case 'skills.versions':
        return { versions: this.versionsOf(params) };
      case 'skills.use_log':
        return { uses: this.usesOf(params) };
      case 'skills.proposals':
        return {
          proposals: [...this.proposals.values()].sort((a, b) => a.created_at - b.created_at),
        };
      case 'skills.propose':
        return { proposal: this.propose(params) };
      case 'skills.apply_proposal':
        return this.applyProposal(params);
      case 'skills.discard_proposal':
        return { discarded: this.discardProposal(params) };
      case 'skills.learn_status':
        return { available: true, network_enabled: this.networkEnabled };
      case 'skills.learn_classify':
        return { source: this.classify(params) };
      case 'skills.references':
        return this.references(params);
      case 'skills.save':
      case 'skills.edit':
        return this.save(params);
      default:
        return invalid(`unknown skills method ${method}`);
    }
  }

  private versionsOf(params: RpcParams): EchoSkillVersion[] {
    const name = params['name'];
    if (typeof name !== 'string' || !name.trim()) {
      throw invalid('name must be a non-empty string');
    }
    return [...(this.versions.get(name.trim()) ?? [])];
  }

  private usesOf(params: RpcParams): EchoSkillUse[] {
    const name = params['name'];
    if (name === undefined || name === null) return [...this.uses];
    if (typeof name !== 'string') throw invalid('name must be a string');
    return this.uses.filter((use) => use.name === name.trim());
  }

  private propose(params: RpcParams): EchoSkillProposal | null {
    const message = params['message'];
    if (typeof message !== 'string' || !message.trim()) {
      throw invalid('message must be a non-empty string');
    }
    if (message.trim().length < 400) return null;
    const topic = 'session-procedure';
    const existing = this.versions.has(topic);
    this.proposalSeq += 1;
    const proposal: EchoSkillProposal = {
      proposal_id: `prop-${this.proposalSeq}`,
      name: topic,
      description: 'Reusable steps from a recent complex task.',
      body: '## Purpose\n\nCapture a reusable procedure.\n',
      action: existing ? 'improve' : 'create',
      created_at: Date.now() / 1000,
    };
    this.proposals.set(proposal.proposal_id, proposal);
    return proposal;
  }

  private applyProposal(params: RpcParams): Record<string, unknown> {
    const id = params['proposal_id'];
    if (typeof id !== 'string') throw invalid('proposal_id must be a string');
    const proposal = this.proposals.get(id);
    if (!proposal) {
      throw invalid('unknown or already resolved proposal');
    }
    this.proposals.delete(id);
    const existing = this.versions.has(proposal.name);
    this.recordVersion(proposal.name, proposal.body, 'skill_md');
    return {
      applied: true,
      proposal_id: id,
      name: proposal.name,
      status: existing ? 'merged' : 'created',
      filename: `skills/${proposal.name}/SKILL.md`,
    };
  }

  private discardProposal(params: RpcParams): boolean {
    const id = params['proposal_id'];
    if (typeof id !== 'string') throw invalid('proposal_id must be a string');
    return this.proposals.delete(id);
  }

  private recordVersion(name: string, content: string, kind: string): number {
    const rows = this.versions.get(name) ?? [];
    const latest = rows[rows.length - 1];
    if (latest && latest.content === content) return latest.version;
    const version = (latest?.version ?? 0) + 1;
    rows.push({ name, version, content, kind, created_at: Date.now() / 1000 });
    this.versions.set(name, rows);
    return version;
  }

  private save(params: RpcParams): Record<string, unknown> {
    const name = params['name'];
    if (typeof name !== 'string' || !name.trim()) {
      throw invalid('name must be a non-empty string');
    }
    const content = params['content'];
    if (typeof content !== 'string' || !content.trim()) {
      throw invalid('content must be a non-empty string');
    }
    const cleaned = slugify(name, 'learned-skill');
    const existing = this.versions.has(cleaned);
    this.recordVersion(cleaned, content, 'skill_md');
    return {
      filename: `skills/${cleaned}/SKILL.md`,
      status: existing ? 'merged' : 'created',
      name: cleaned,
    };
  }

  /** Offline-first `/learn` classification with the kernel's refusal laws. */
  private classify(params: RpcParams): EchoLearnSource {
    const argument = params['argument'];
    if (typeof argument !== 'string') throw invalid('argument must be a string');
    const history = params['history'];
    if (history !== undefined && history !== null && !Array.isArray(history)) {
      throw invalid('history must be a list when given');
    }
    const trimmed = argument.trim();
    const lowered = trimmed.toLowerCase();
    if (!trimmed || ['conversation', 'chat', 'session'].includes(lowered)) {
      const lines = ((history as Array<Record<string, unknown>> | undefined) ?? [])
        .filter((item) => item && typeof item === 'object')
        .map((item) => {
          const content = item['content'];
          return typeof content === 'string' ? content : '';
        })
        .filter((line) => line.trim());
      if (lines.length === 0) throw emptySourceRefusal('conversation');
      const text = lines.join('\n');
      const topic = slugify(text, 'conversation-notes');
      return {
        kind: 'conversation',
        topic,
        text,
        existing: this.versions.has(topic) ? topic : null,
      };
    }
    if (
      lowered.startsWith('http://') ||
      lowered.startsWith('https://') ||
      lowered.startsWith('url ')
    ) {
      if (!this.networkEnabled) throw urlOffRefusal();
      const address = lowered.startsWith('url ') ? trimmed.slice(4).trim() : trimmed;
      const topic = slugify(address.replace(/^https?:\/\//, ''), 'web-source');
      return {
        kind: 'url',
        topic,
        text: `Fetched page for ${address}`,
        existing: this.versions.has(topic) ? topic : null,
      };
    }
    if (trimmed.includes('/')) {
      const isFolder = trimmed.endsWith('/');
      const leaf = trimmed.replace(/\/+$/, '').split('/').pop() ?? trimmed;
      const topic = slugify(leaf, isFolder ? 'local-corpus' : 'local-source');
      return {
        kind: isFolder ? 'corpus' : 'path',
        topic,
        text: `Loaded ${trimmed}`,
        existing: this.versions.has(topic) ? topic : null,
      };
    }
    const topic = slugify(trimmed, 'pasted-notes');
    return {
      kind: 'notes',
      topic,
      text: trimmed,
      existing: this.versions.has(topic) ? topic : null,
    };
  }

  private references(params: RpcParams): Record<string, unknown> {
    const name = params['name'];
    if (typeof name !== 'string' || !name.trim()) {
      throw invalid('name must be a non-empty string');
    }
    const cleaned = slugify(name, '');
    if (!this.versions.has(cleaned)) {
      throw invalid(`unknown skill '${name.trim()}'`);
    }
    const rows = this.referenceFiles.get(cleaned) ?? [];
    return { references: [...rows], name: cleaned, filename: `skills/${cleaned}/SKILL.md` };
  }
}
