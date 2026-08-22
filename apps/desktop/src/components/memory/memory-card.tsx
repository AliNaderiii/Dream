/**
 * One memory row in the explorer list.
 *
 * The whole card is a button so it is reachable by keyboard and announced as a
 * single control; the content preview is clamped rather than truncated with a
 * substring, which keeps Persian text shaping intact.
 */

import { Archive } from 'lucide-react';

import { KindBadge } from '@/components/memory/kind-badge';
import { ImportanceStars } from '@/components/memory/importance-stars';
import { MemoryScore } from '@/components/memory/memory-score';
import { sanitizeMemoryText, toStars } from '@/lib/bridge/memory';
import { useTranslation } from '@/lib/i18n';
import type { BridgeMemory } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';
import { relativeTime } from '@/utils/time';

interface MemoryCardProps {
  memory: BridgeMemory;
  selected?: boolean;
  onSelect: (memory: BridgeMemory) => void;
}

export function MemoryCard({ memory, selected, onSelect }: MemoryCardProps) {
  const { t } = useTranslation('memory');
  return (
    <button
      type="button"
      onClick={() => onSelect(memory)}
      aria-current={selected ? 'true' : undefined}
      className={cn(
        'flex w-full flex-col gap-2 rounded-lg border p-3 text-start transition-colors duration-fast ease-standard',
        selected
          ? 'border-accent bg-accent-soft'
          : 'border-border-default bg-surface hover:bg-surface-2',
      )}
    >
      <div className="flex items-center gap-2">
        <KindBadge kind={memory.kind} />
        {memory.archived && (
          <span className="inline-flex items-center gap-1 text-micro text-fg-muted">
            <Archive className="size-3" aria-hidden />
            {t('archived')}
          </span>
        )}
        <span className="ms-auto shrink-0 text-micro text-fg-muted">
          {relativeTime(memory.created_at)}
        </span>
      </div>

      <p className="line-clamp-3 whitespace-pre-wrap break-words text-body text-fg-primary">
        {sanitizeMemoryText(memory.content)}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <ImportanceStars value={toStars(memory.importance)} compact />
        {memory.tags.slice(0, 3).map((tag) => (
          <span
            key={tag}
            className="rounded-full bg-surface-2 px-2 py-0.5 text-micro text-fg-muted"
          >
            {tag}
          </span>
        ))}
      </div>
      <MemoryScore memory={memory} compact />
    </button>
  );
}
