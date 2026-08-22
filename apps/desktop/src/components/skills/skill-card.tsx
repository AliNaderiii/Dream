/**
 * One skill row in the manager list.
 *
 * The card body selects the skill; the enable/disable switch and the batch
 * checkbox are separate controls so each is independently focusable and the
 * toggle never fires as a side effect of selecting.
 */

import { Check } from 'lucide-react';

import type { BridgeSkillEx } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';
import { absoluteDate } from '@/utils/time';

interface SkillCardProps {
  skill: BridgeSkillEx;
  selected: boolean;
  checked: boolean;
  /** Unix seconds; 0 when the file's mtime is unknown. */
  createdAt?: number;
  onSelect: (skill: BridgeSkillEx) => void;
  onToggleEnabled: (skill: BridgeSkillEx, enabled: boolean) => void;
  onToggleChecked: (skill: BridgeSkillEx, checked: boolean) => void;
}

export function SkillCard({
  skill,
  selected,
  checked,
  createdAt,
  onSelect,
  onToggleEnabled,
  onToggleChecked,
}: SkillCardProps) {
  const { t } = useTranslation('skills');
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3 transition-colors duration-fast',
        selected ? 'border-accent bg-accent-soft' : 'border-border-default bg-surface',
      )}
    >
      <label className="flex cursor-pointer items-center pt-0.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onToggleChecked(skill, event.target.checked)}
          aria-label={t('card.selectExport', { name: skill.name })}
          className="size-4 accent-[var(--accent-solid)]"
        />
      </label>

      <button
        type="button"
        onClick={() => onSelect(skill)}
        aria-current={selected ? 'true' : undefined}
        className="min-w-0 flex-1 text-start"
      >
        <div className="flex items-center gap-2">
          <span className="truncate text-body font-medium text-fg-primary">{skill.name}</span>
          {!skill.enabled && (
            <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-micro text-fg-muted">
              {t('disabled')}
            </span>
          )}
        </div>
        <p className="line-clamp-2 text-caption text-fg-secondary">{skill.description}</p>
        <p className="pt-1 text-micro text-fg-muted">
          {t('card.stepCount', { count: skill.steps.length })}
          {createdAt ? ` · ${t('added', { date: absoluteDate(createdAt) })}` : ''}
        </p>
      </button>

      <button
        type="button"
        role="switch"
        aria-checked={skill.enabled}
        aria-label={t(skill.enabled ? 'card.disable' : 'card.enable', { name: skill.name })}
        onClick={() => onToggleEnabled(skill, !skill.enabled)}
        className={cn(
          'relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors duration-fast ease-standard',
          skill.enabled ? 'bg-accent' : 'bg-sunken',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute top-0.5 flex size-4 items-center justify-center rounded-full bg-white transition-[inset-inline-start] duration-fast ease-standard',
            skill.enabled ? 'start-[1.125rem]' : 'start-0.5',
          )}
        >
          {skill.enabled && <Check className="size-2.5 text-accent" aria-hidden />}
        </span>
      </button>
    </div>
  );
}
