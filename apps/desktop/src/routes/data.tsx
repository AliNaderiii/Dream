/**
 * Data workbench landing (P-09): the dataset registry. Lists every ingested
 * dataset with shape and status, links into the per-dataset workbench, and
 * offers ingestion by file path.
 */

import { BarChart3, Database, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { EmptyState } from '@/components/shared/empty-state';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { deleteDataset, listDatasets, loadDataset } from '@/lib/bridge/data-science';
import { useBridge } from '@/lib/bridge/hooks';
import type { DatasetSummaryDto } from '@/lib/bridge/types';
import { formatDateTime } from '@/utils/format';

function DatasetRow({ dataset, onDelete }: { dataset: DatasetSummaryDto; onDelete: () => void }) {
  const { t } = useTranslation('data');
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border-default bg-surface p-3 hover:bg-surface-2">
      <Database className="size-5 shrink-0 text-fg-muted" aria-hidden />
      <Link
        to={`/data/${dataset.dataset_id}`}
        className="flex min-w-0 flex-1 flex-col gap-0.5 outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span className="flex items-center gap-2">
          <span className="truncate text-body font-medium">{dataset.name}</span>
          <Badge variant="neutral">{dataset.format}</Badge>
          {dataset.cleaned && <Badge variant="success">{t('cleaned')}</Badge>}
        </span>
        <span className="text-caption text-fg-muted">
          {t('rows', { rows: dataset.shape[0].toLocaleString(), cols: dataset.shape[1] })} ·{' '}
          {formatDateTime(dataset.created_at)}
        </span>
      </Link>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={t('deleteDataset', { name: dataset.name })}
        onClick={onDelete}
      >
        <Trash2 aria-hidden />
      </Button>
    </li>
  );
}

export function DataRoute() {
  const { t } = useTranslation('data');
  const { client } = useBridge();
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState<DatasetSummaryDto[] | null>(null);
  const [filePath, setFilePath] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await listDatasets(client);
    setDatasets(result.datasets);
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const result = await listDatasets(client);
      if (!cancelled) setDatasets(result.datasets);
    };
    load().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client]);

  const ingest = async () => {
    if (!filePath.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const dataset = await loadDataset(client, filePath.trim());
      setFilePath('');
      void navigate(`/data/${dataset.dataset_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (datasetId: string) => {
    await deleteDataset(client, datasetId);
    await refresh();
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-h1 font-bold">{t('title')}</h2>
          <p className="text-body text-fg-secondary">{t('subtitle')}</p>
        </div>
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void ingest();
          }}
        >
          <input
            type="text"
            aria-label={t('load')}
            placeholder={t('ingestPlaceholder')}
            value={filePath}
            onChange={(event) => setFilePath(event.target.value)}
            className="h-8 w-72 rounded-md border border-border-default bg-surface px-2.5 text-body outline-none focus:border-accent ltr-island"
          />
          <Button type="submit" variant="primary" size="md" disabled={busy || !filePath.trim()}>
            <Plus aria-hidden />
            {t('load')}
          </Button>
        </form>
      </header>

      {error && (
        <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
          {error}
        </p>
      )}

      {datasets === null ? (
        <p className="text-body text-fg-muted">{t('loading')}</p>
      ) : datasets.length === 0 ? (
        <EmptyState icon={BarChart3} title={t('noDatasets')} description={t('noDatasetsDesc')} />
      ) : (
        <ul className="flex flex-col gap-2 overflow-y-auto">
          {datasets.map((dataset) => (
            <DatasetRow
              key={dataset.dataset_id}
              dataset={dataset}
              onDelete={() => void remove(dataset.dataset_id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
