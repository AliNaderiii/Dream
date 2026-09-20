/**
 * Skill-file highlight tokenizer.
 *
 * Kept in a module without components so React Fast Refresh stays intact for
 * `skill-code.tsx` (react-refresh/only-export-components).
 */

/** The line classes the highlighter distinguishes. */
export type SkillTokenKind = 'key' | 'value' | 'step-marker' | 'step' | 'text';

/** One highlighted span within a line. */
export interface SkillToken {
  kind: SkillTokenKind;
  text: string;
}

const KEY_RE = /^(\s*)(name|description|steps)(\s*:)(.*)$/i;
const STEP_RE = /^(\s*)((?:[-*]|\d+[.)])\s*)(.*)$/;

/** Split one line of a skill file into highlight tokens. */
export function tokenizeSkillLine(line: string): SkillToken[] {
  const keyMatch = KEY_RE.exec(line);
  if (keyMatch) {
    const [, indent, key, colon, rest] = keyMatch;
    const tokens: SkillToken[] = [];
    if (indent) tokens.push({ kind: 'text', text: indent });
    tokens.push({ kind: 'key', text: `${key}${colon}` });
    if (rest) tokens.push({ kind: 'value', text: rest });
    return tokens;
  }

  const stepMatch = STEP_RE.exec(line);
  if (stepMatch) {
    const [, indent, marker, rest] = stepMatch;
    const tokens: SkillToken[] = [];
    if (indent) tokens.push({ kind: 'text', text: indent });
    tokens.push({ kind: 'step-marker', text: marker });
    if (rest) tokens.push({ kind: 'step', text: rest });
    return tokens;
  }

  return [{ kind: 'text', text: line }];
}
