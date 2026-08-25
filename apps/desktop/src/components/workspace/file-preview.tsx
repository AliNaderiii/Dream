import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import type { WorkspacePreview } from '@/lib/bridge/workspace';

function Chart({ preview }: { preview: WorkspacePreview }) {
  const chart = preview.chart;
  if (!chart || !chart.values.length) return null;
  const maximum = Math.max(...chart.values.map(Math.abs), 1);
  return (
    <figure aria-label={chart.y} className="rounded-lg border border-border-default bg-surface p-3">
      <div className="flex h-40 items-end gap-2" role="img" aria-label={`${chart.x} ${chart.y}`}>
        {chart.labels.map((label, index) => {
          const value = chart.values[index] ?? 0;
          return (
            <div
              key={`${label}-${index}`}
              className="flex min-w-10 flex-1 flex-col items-center justify-end gap-1"
            >
              <span className="text-micro text-fg-muted">{value}</span>
              <span
                className="w-full rounded-t bg-accent"
                style={{ height: `${Math.max(3, (Math.abs(value) / maximum) * 110)}px` }}
              />
              <span className="max-w-full truncate text-micro">{label}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

export function FilePreview({ preview }: { preview: WorkspacePreview | null }) {
  const { t } = useTranslation('workspace');
  if (!preview) {
    return <p className="text-body text-fg-muted">{t('preview.empty')}</p>;
  }
  return (
    <article className="flex flex-col gap-3" aria-label={t('preview.title')}>
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-h3 font-semibold">{preview.name}</h3>
        <Badge variant="neutral">{preview.type}</Badge>
        {preview.executed === false && <Badge variant="success">{t('preview.safe')}</Badge>}
        {preview.truncated && <Badge variant="warning">{t('preview.truncated')}</Badge>}
      </header>
      {preview.chart && <Chart preview={preview} />}
      {preview.table && (
        <div className="overflow-x-auto rounded-lg border border-border-default">
          <table className="w-full text-start text-caption">
            <thead className="bg-surface-2">
              <tr>
                {preview.table.columns.map((column) => (
                  <th key={column} scope="col" className="px-3 py-2 text-start font-semibold">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.table.rows.map((row, index) => (
                <tr key={index} className="border-t border-border-default">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 font-mono">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {preview.html ? (
        <div className="rounded-lg border border-border-default p-3 text-caption">
          {preview.text}
        </div>
      ) : (
        preview.text && (
          <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-micro">
            <code>{preview.text}</code>
          </pre>
        )
      )}
      {preview.warning && <p className="text-micro text-warning-fg">{preview.warning}</p>}
    </article>
  );
}
