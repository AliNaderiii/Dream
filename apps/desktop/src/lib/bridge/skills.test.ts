import { unzipSync, strFromU8 } from 'fflate';
import { describe, expect, it } from 'vitest';

import { BridgeClient, EchoBridgeTransport } from '@/lib/bridge/client';
import {
  buildSkillZip,
  deleteSkill,
  exportFilename,
  exportSkill,
  getSkill,
  installSkill,
  listSkills,
  parseSkillText,
  renderSkillText,
  setSkillEnabled,
  validateSkillContent,
} from '@/lib/bridge/skills';

const VALID = [
  'name: weekly report',
  'description: Summarise the week.',
  'steps:',
  '- Collect sessions',
  '- Write it up',
].join('\n');

function client(): BridgeClient {
  return new BridgeClient(new EchoBridgeTransport());
}

describe('parseSkillText', () => {
  it('reads the three sections', () => {
    const parsed = parseSkillText(VALID);
    expect(parsed).toEqual({
      name: 'weekly report',
      description: 'Summarise the week.',
      steps: ['Collect sessions', 'Write it up'],
    });
  });

  it('accepts numbered steps', () => {
    const parsed = parseSkillText('name: a\ndescription: b\nsteps:\n1. first\n2) second');
    expect(parsed?.steps).toEqual(['first', 'second']);
  });

  it('returns null when a section is missing', () => {
    expect(parseSkillText('name: a\ndescription: b')).toBeNull();
    expect(parseSkillText('steps:\n- only steps')).toBeNull();
  });

  it('round-trips through renderSkillText', () => {
    const parsed = parseSkillText(VALID);
    expect(parseSkillText(renderSkillText(parsed!))).toEqual(parsed);
  });
});

describe('validateSkillContent', () => {
  it('accepts a well-formed skill', () => {
    const result = validateSkillContent(VALID);
    expect(result.ok).toBe(true);
    expect(result.errors).toEqual([]);
    expect(result.parsed?.name).toBe('weekly report');
  });

  it('rejects an empty file', () => {
    expect(validateSkillContent('  ').ok).toBe(false);
  });

  it('rejects content over the 100 KB cap', () => {
    const bloated = `${VALID}\n- ${'x'.repeat(100 * 1024)}`;
    const result = validateSkillContent(bloated);
    expect(result.ok).toBe(false);
    expect(result.errors.join(' ')).toMatch(/100 KB/);
  });

  it('rejects absolute paths', () => {
    const result = validateSkillContent(`${VALID}\n- open /etc/passwd`);
    expect(result.ok).toBe(false);
    expect(result.errors.join(' ')).toMatch(/absolute file paths/);
  });

  it('rejects parent-directory traversal', () => {
    const result = validateSkillContent(`${VALID}\n- read ../../secrets`);
    expect(result.ok).toBe(false);
    expect(result.errors.join(' ')).toMatch(/\.\./);
  });

  it('rejects dangerous imports', () => {
    const result = validateSkillContent('name: x\ndescription: y\nsteps:\nimport subprocess');
    expect(result.ok).toBe(false);
    expect(result.errors.join(' ')).toMatch(/import statements/);
  });

  it('does not flag prose that merely mentions importing', () => {
    const result = validateSkillContent(
      'name: import test\ndescription: Import a CSV file.\nsteps:\n- Import the rows',
    );
    expect(result.ok).toBe(true);
  });

  it('rejects a file missing required sections', () => {
    const result = validateSkillContent('just some text');
    expect(result.ok).toBe(false);
    expect(result.errors.join(' ')).toMatch(/name:/);
  });
});

describe('exportFilename', () => {
  it('slugifies the skill name', () => {
    expect(exportFilename('Weekly Report')).toBe('weekly-report.dream-skill.txt');
    expect(exportFilename('  ')).toBe('skill.dream-skill.txt');
  });
});

describe('buildSkillZip', () => {
  it('packs every skill and de-duplicates colliding names', () => {
    const zip = buildSkillZip([
      { name: 'alpha', content: 'a' },
      { name: 'alpha', content: 'b' },
    ]);
    const entries = unzipSync(zip);
    const names = Object.keys(entries).sort();
    expect(names).toHaveLength(2);
    expect(names.map((n) => strFromU8(entries[n])).sort()).toEqual(['a', 'b']);
  });
});

describe('skill RPC wrappers over the echo transport', () => {
  it('lists skills with their enabled flag', async () => {
    const result = await listSkills(client());
    expect(result.skills.length).toBeGreaterThan(0);
    expect(result.skills.some((s) => s.enabled)).toBe(true);
    expect(result.skills.some((s) => !s.enabled)).toBe(true);
  });

  it('fetches full detail including the rendered file', async () => {
    const c = client();
    const detail = await getSkill(c, 'weekly report');
    expect(detail?.content).toMatch(/^name: weekly report/);
    expect(await getSkill(c, 'nothing at all')).toBeNull();
  });

  it('toggles enabled state', async () => {
    const c = client();
    const off = await setSkillEnabled(c, 'weekly report', false);
    expect(off.enabled).toBe(false);
    expect((await getSkill(c, 'weekly report'))?.enabled).toBe(false);
    expect((await setSkillEnabled(c, 'weekly report', true)).enabled).toBe(true);
  });

  it('reports a name conflict instead of clobbering', async () => {
    const c = client();
    const conflict = await installSkill(c, VALID);
    expect(conflict.status).toBe('conflict');

    const forced = await installSkill(c, VALID, { overwrite: true });
    expect(forced.status).toBe('installed');
  });

  it('installs a new skill and deletes it again', async () => {
    const c = client();
    const body = 'name: fresh\ndescription: Something new.\nsteps:\n- do it';
    expect((await installSkill(c, body)).status).toBe('installed');
    expect((await listSkills(c)).skills.some((s) => s.name === 'fresh')).toBe(true);

    const exported = await exportSkill(c, 'fresh');
    expect(exported.content).toMatch(/do it/);

    await deleteSkill(c, 'fresh');
    expect((await listSkills(c)).skills.some((s) => s.name === 'fresh')).toBe(false);
  });
});
