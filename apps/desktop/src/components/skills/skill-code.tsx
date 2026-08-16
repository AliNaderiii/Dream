/**
 * Dependency-free highlighter for skill files.
 *
 * A skill is a tiny three-section format (`name:`, `description:`, `steps:`
 * followed by list items), so a full editor would be far more machinery than
 * the grammar deserves. The tokeniser below classifies each line and the
 * renderer paints it with design tokens.
 */

import { Fragment } from 'react';

import { cn } from '@/utils/cn';

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

const TOKEN_CLASS: Record<SkillTokenKind, string> = {
  key: 'font-semibold text-accent-text',
  value: 'text-fg-primary',
  'step-marker': 'text-chart-2',
  step: 'text-fg-primary',
  text: 'text-fg-secondary',
};

interface SkillCodeProps {
  content: string;
  className?: string;
}

/** Read-only, highlighted view of a skill file. */
export function SkillCode({ content, className }: SkillCodeProps) {
  const lines = content.split(/\r?\n/);
  return (
    <pre
      className={cn(
        'selectable ltr-island overflow-x-auto rounded-md border border-border-default bg-sunken p-3 text-code leading-[var(--text-code--line-height)]',
        className,
      )}
    >
      <code>
        {lines.map((line, index) => (
          <Fragment key={index}>
            {tokenizeSkillLine(line).map((token, tokenIndex) => (
              <span key={tokenIndex} className={TOKEN_CLASS[token.kind]}>
                {token.text}
              </span>
            ))}
            {index < lines.length - 1 && '\n'}
          </Fragment>
        ))}
      </code>
    </pre>
  );
}
