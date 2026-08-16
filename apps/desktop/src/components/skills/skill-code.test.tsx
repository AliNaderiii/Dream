import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SkillCode, tokenizeSkillLine } from '@/components/skills/skill-code';

describe('tokenizeSkillLine', () => {
  it('marks the section keys', () => {
    expect(tokenizeSkillLine('name: weekly report')).toEqual([
      { kind: 'key', text: 'name:' },
      { kind: 'value', text: ' weekly report' },
    ]);
    expect(tokenizeSkillLine('description: x')[0]?.kind).toBe('key');
    expect(tokenizeSkillLine('steps:')).toEqual([{ kind: 'key', text: 'steps:' }]);
  });

  it('splits the step marker from the step body', () => {
    expect(tokenizeSkillLine('- do the thing')).toEqual([
      { kind: 'step-marker', text: '- ' },
      { kind: 'step', text: 'do the thing' },
    ]);
    expect(tokenizeSkillLine('1. first')[0]?.kind).toBe('step-marker');
  });

  it('falls back to plain text', () => {
    expect(tokenizeSkillLine('a loose sentence')).toEqual([
      { kind: 'text', text: 'a loose sentence' },
    ]);
  });

  it('preserves leading indentation', () => {
    expect(tokenizeSkillLine('  - indented')[0]).toEqual({ kind: 'text', text: '  ' });
  });
});

describe('SkillCode', () => {
  it('renders every line of the file', () => {
    render(<SkillCode content={'name: a\ndescription: b\nsteps:\n- one'} />);
    expect(screen.getByText('name:')).toBeInTheDocument();
    expect(screen.getByText('one')).toBeInTheDocument();
  });
});
