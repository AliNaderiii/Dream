/**
 * Figure gallery — grid view of charts from section.charts.
 */

import { BarChart3, Image as ImageIcon } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import type { Section } from '@/lib/bridge/research-types';

function FigurePlaceholder({ title }: { title: string }) {
  return (
    <div className="flex aspect-video items-center justify-center rounded-lg bg-surface-2">
      <div className="flex flex-col items-center gap-2 text-fg-muted">
        <BarChart3 className="size-8" aria-hidden />
        <span className="text-micro text-center">{title}</span>
      </div>
    </div>
  );
}

export function FigureGallery({ charts, sections }: { charts: string[]; sections: Section[] }) {
  const { t } = useTranslation('research');
  const [selected, setSelected] = useState<string | null>(null);

  if (charts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <ImageIcon className="size-8 text-fg-muted" aria-hidden />
        <p className="text-body text-fg-muted">{t('figures.none')}</p>
      </div>
    );
  }

  // Map charts to their source sections
  const chartItems = charts.map((chart) => {
    const section = sections.find((s) => s.charts.includes(chart));
    return { chart, section };
  });

  return (
    <div className="flex flex-col gap-4">
      <div
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        role="list"
        aria-label={t('figures.gallery')}
      >
        {chartItems.map(({ chart, section }) => (
          <button
            key={chart}
            type="button"
            onClick={() => setSelected(chart)}
            className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3 text-start transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <FigurePlaceholder title={chart} />
            <span className="text-caption font-semibold">{chart}</span>
            {section && <Badge variant="neutral">{section.title}</Badge>}
          </button>
        ))}
      </div>

      {selected && (
        <div
          className="fixed inset-0 z-modal flex items-center justify-center bg-black/50 p-8"
          role="dialog"
          aria-modal="true"
          onClick={() => setSelected(null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setSelected(null);
          }}
        >
          <div
            className="flex max-w-3xl flex-col gap-4 rounded-xl bg-surface p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <FigurePlaceholder title={selected} />
            <p className="text-caption font-semibold">{selected}</p>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="self-end text-caption text-fg-muted hover:text-fg-primary"
              autoFocus
            >
              {t('close')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
