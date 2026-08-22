import type { BridgeSkillEx } from '@/lib/bridge/types';
import type { SkillValidationIssue } from '@/lib/bridge/skills';

/** Stable view ordering for the installed-skill roster. */
export function sortSkills(skills: readonly BridgeSkillEx[]): BridgeSkillEx[] {
  return [...skills].sort((left, right) => left.name.localeCompare(right.name));
}

/** Pure optimistic transition shared by success and rollback paths. */
export function withSkillEnabled(
  skills: readonly BridgeSkillEx[],
  skillName: string,
  enabled: boolean,
): BridgeSkillEx[] {
  return skills.map((skill) =>
    skill.name === skillName && skill.enabled !== enabled ? { ...skill, enabled } : skill,
  );
}

/** Keep selection on a renamed/saved skill only when it still exists. */
export function selectedSkillAfterSave(
  skills: readonly BridgeSkillEx[],
  savedName: string | undefined,
  previousName: string | null,
): string | null {
  if (!savedName) return previousName;
  return skills.some((skill) => skill.name === savedName) ? savedName : previousName;
}

/** Locale key/options are pure data so both import and edit paths render identical errors. */
export function validationMessageDescriptor(issue: SkillValidationIssue): {
  key: string;
  options: Record<string, string>;
} {
  return {
    key: `validation.${issue.code}`,
    options: issue.sizeKb ? { size: issue.sizeKb } : {},
  };
}
