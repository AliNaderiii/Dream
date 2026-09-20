/**
 * Dependency-free highlighter for skill files.
 *
 * A skill is a tiny three-section format (`name:`, `description:`, `steps:`
 * followed by list items), so a full editor would be far more machinery than
 * the grammar deserves. The tokeniser below classifies each line and the
 * renderer paints it with design tokens.
 */

import { Fragment } from 'react';

import { tokenizeSkillLine } from '@/components/skills/skill-tokens';
import type { SkillTokenKind } from '@/components/skills/skill-tokens';
import { cn } from '@/utils/cn';

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
