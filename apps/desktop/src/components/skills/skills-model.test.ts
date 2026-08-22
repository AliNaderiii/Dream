import { describe, expect, it } from 'vitest';

import {
  selectedSkillAfterSave,
  sortSkills,
  validationMessageDescriptor,
  withSkillEnabled,
} from '@/components/skills/skills-model';
import type { BridgeSkillEx } from '@/lib/bridge/types';

function skill(name: string, enabled: boolean): BridgeSkillEx {
  return {
    name,
    description: `${name} description`,
    filename: `${name}.dream-skill.txt`,
    enabled,
    steps: ['step'],
  };
}

describe('skills model', () => {
  it('sorts a copy without mutating bridge order', () => {
    const input = [skill('Zulu', true), skill('Alpha', false)];
    expect(sortSkills(input).map((item) => item.name)).toEqual(['Alpha', 'Zulu']);
    expect(input.map((item) => item.name)).toEqual(['Zulu', 'Alpha']);
  });

  it('applies and rolls back the same optimistic enabled transition', () => {
    const input = [skill('Alpha', true), skill('Beta', false)];
    const optimistic = withSkillEnabled(input, 'Alpha', false);
    expect(optimistic[0].enabled).toBe(false);
    expect(optimistic[1]).toBe(input[1]);
    expect(withSkillEnabled(optimistic, 'Alpha', true)[0].enabled).toBe(true);
    expect(input[0].enabled).toBe(true);
  });

  it('retains selection when a parsed rename is absent from the refreshed list', () => {
    const skills = [skill('Existing', true)];
    expect(selectedSkillAfterSave(skills, 'Existing', 'Old')).toBe('Existing');
    expect(selectedSkillAfterSave(skills, 'Missing', 'Old')).toBe('Old');
    expect(selectedSkillAfterSave(skills, undefined, 'Old')).toBe('Old');
  });

  it('turns validation issues into locale descriptors without English UI text', () => {
    expect(validationMessageDescriptor({ code: 'absolutePath' })).toEqual({
      key: 'validation.absolutePath',
      options: {},
    });
    expect(validationMessageDescriptor({ code: 'tooLarge', sizeKb: '101.5' })).toEqual({
      key: 'validation.tooLarge',
      options: { size: '101.5' },
    });
  });
});
