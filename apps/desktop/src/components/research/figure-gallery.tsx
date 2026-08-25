/**
 * Figure gallery — grid view of all report figures with captions and
 * source step links.
 */

import { BarChart3, Image as ImageIcon } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import type { ResearchFigure } from '@/lib/bridge/research-types';

/** Placeholder SVG for echo-mode figures (no real images in browser dev). */
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

function FigureCard({ figure, onClick }: { figure: ResearchFigure; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3 text-start transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <FigurePlaceholder title={figure.title} />
      <div className="flex flex-col gap-1">
        <span className="text-caption font-semibold">{figure.title}</span>
        <p className="line-clamp-2 text-micro text-fg-muted">{figure.caption}</p>
      </div>
      {figure.source_step_id && <Badge variant="neutral">{figure.source_step_id}</Badge>}
    </button>
  );
}

export function FigureGallery({ figures }: { figures: ResearchFigure[] }) {
  const { t } = useTranslation('research');
  const [selected, setSelected] = useState<ResearchFigure | null>(null);

  if (figures.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <ImageIcon className="size-8 text-fg-muted" aria-hidden />
        <p className="text-body text-fg-muted">{t('figures.none')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Grid */}
      <div
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        role="list"
        aria-label={t('figures.gallery')}
      >
        {figures.map((figure) => (
          <FigureCard key={figure.figure_id} figure={figure} onClick={() => setSelected(figure)} />
        ))}
      </div>

      {/* Lightbox */}
      {selected && (
        <div
          className="fixed inset-0 z-modal flex items-center justify-center bg-black/50 p-8"
          role="dialog"
          aria-modal="true"
          aria-label={selected.title}
          onClick={() => setSelected(null)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setSelected(null);
          }}
        >
          <div
            className="flex max-w-3xl flex-col gap-4 rounded-xl bg-surface p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <FigurePlaceholder title={selected.title} />
            <div>
              <h4 className="text-body font-semibold">{selected.title}</h4>
              <p className="mt-1 text-caption text-fg-muted">{selected.caption}</p>
            </div>
            {selected.source_step_id && (
              <div className="flex items-center gap-2 text-micro text-fg-muted">
                <span>{t('figures.source')}:</span>
                <Badge variant="accent">{selected.source_step_id}</Badge>
              </div>
            )}
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
