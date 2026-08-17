/**
 * Chart gallery: renders generated charts (interactive HTML embeds when the
 * sidecar produced them, spec summaries otherwise) with download buttons,
 * plus the ranked auto-chart suggestions with one-click render.
 */

import { BarChart3, Download, Sparkles } from 'lucide-react';

import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatBytes, preferredDownload, reduceChartGallery } from '@/lib/bridge/data-science';
import type { ChartResultDto, ChartSpecDto } from '@/lib/bridge/types';

interface ChartGalleryProps {
  charts: ChartResultDto[];
  suggestions: ChartSpecDto[];
  onRender: (spec: ChartSpecDto) => void;
  rendering: boolean;
  /** Resolves a sidecar-relative chart path to a URL the webview can load. */
  resolveFileUrl?: (path: string) => string | null;
}

function ChartCard({
  chart,
  resolveFileUrl,
}: {
  chart: ChartResultDto;
  resolveFileUrl?: (path: string) => string | null;
}) {
  const html = chart.files.html ? resolveFileUrl?.(chart.files.html) : null;
  const png = chart.files.png ? resolveFileUrl?.(chart.files.png) : null;
  const download = preferredDownload(chart);
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 truncate">
          <Badge variant="accent">{chart.spec.type}</Badge>
          <span className="truncate text-body font-medium">
            {chart.spec.title ||
              `${chart.spec.y ?? ''} ${chart.spec.x ? `by ${chart.spec.x}` : ''}`.trim() ||
              chart.chart_id}
          </span>
        </span>
        {download && (
          <Button asChild size="sm" variant="ghost" aria-label={`Download ${download.format}`}>
            <a href={resolveFileUrl?.(download.path) ?? '#'} download>
              <Download aria-hidden />
              {download.format.toUpperCase()}
            </a>
          </Button>
        )}
      </div>
      {html ? (
        <iframe
          title={`Chart ${chart.chart_id}`}
          src={html}
          sandbox="allow-scripts"
          className="h-64 w-full rounded-md border border-border-default bg-white"
        />
      ) : png ? (
        <img
          src={png}
          alt={chart.spec.title ?? `${chart.spec.type} chart`}
          className="h-64 w-full rounded-md border border-border-default object-contain"
        />
      ) : (
        <div className="flex h-32 items-center justify-center rounded-md border border-dashed border-border-default text-caption text-fg-muted">
          Preview available when the sidecar is running.
        </div>
      )}
      <div className="flex flex-wrap gap-2 text-micro text-fg-muted">
        {Object.entries(chart.sizes).map(([format, size]) => (
          <span key={format} className="tabular">
            {format}: {formatBytes(size)}
          </span>
        ))}
      </div>
    </li>
  );
}

export function ChartGallery({
  charts,
  suggestions,
  onRender,
  rendering,
  resolveFileUrl,
}: ChartGalleryProps) {
  const gallery = reduceChartGallery(charts);
  return (
    <div className="flex flex-col gap-4">
      {suggestions.length > 0 && (
        <section aria-label="Suggested charts">
          <h3 className="mb-2 flex items-center gap-1.5 text-body font-semibold">
            <Sparkles className="size-4 text-accent" aria-hidden /> Suggested charts
          </h3>
          <ul className="flex flex-wrap gap-2">
            {suggestions.map((spec, index) => (
              <li key={`${spec.type}-${spec.x ?? ''}-${spec.y ?? ''}-${index}`}>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={rendering}
                  onClick={() => onRender(spec)}
                  title={spec.reason}
                >
                  <BarChart3 aria-hidden />
                  {spec.type}
                  {spec.x ? `: ${spec.x}` : ''}
                  {spec.y ? ` × ${spec.y}` : ''}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {gallery.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No charts yet"
          description="Render a suggested chart above, or ask the agent to build one in chat."
        />
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {gallery.map((chart) => (
            <ChartCard key={chart.chart_id} chart={chart} resolveFileUrl={resolveFileUrl} />
          ))}
        </ul>
      )}
    </div>
  );
}
