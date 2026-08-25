import { BarChart3, Database, RotateCcw, Search, Send } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Input, Textarea } from '@/components/ui/input';
import {
  askDataQa,
  createDataQaSession,
  discoverDataQa,
  resetDataQa,
  type DataQaCandidate,
  type DataQaFinalAnswer,
  type DataQaSession,
} from '@/lib/bridge/dataqa';
import { useTranslation } from '@/lib/i18n';

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return '—';
  }
}

function EvidenceTable({ answer }: { answer: DataQaFinalAnswer }) {
  const rows = answer.evidence.rows;
  const columns = answer.evidence.columns ?? (rows[0] ? Object.keys(rows[0]) : []);
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full text-start text-caption">
        <thead className="bg-surface-2">
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className="px-3 py-2 text-start font-semibold">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((row, index) => (
            <tr key={index} className="border-t border-border-default">
              {columns.map((column) => (
                <td key={column} className="px-3 py-2 font-mono">
                  {displayValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceChart({ answer }: { answer: DataQaFinalAnswer }) {
  const chart = answer.chart;
  const rows = answer.evidence.rows;
  const columns = answer.evidence.columns ?? [];
  const values = rows.map((row) => Number(row[columns.at(-1) ?? ''])).filter(Number.isFinite);
  const maximum = Math.max(...values.map(Math.abs), 1);
  if (!chart) return null;
  if (chart.svg) {
    return (
      <figure
        aria-label={chart.consistency}
        className="rounded-lg border border-border-default bg-surface p-3"
      >
        <img
          className="h-auto max-h-80 w-full"
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(chart.svg)}`}
          alt={chart.consistency}
        />
        <figcaption className="mt-2 flex items-center gap-2 text-micro text-fg-muted">
          <Badge variant="success">validated</Badge>
          {chart.consistency}
        </figcaption>
      </figure>
    );
  }
  if (chart.type !== 'bar' || columns.length < 2) return null;
  return (
    <figure
      aria-label={chart.consistency}
      className="rounded-lg border border-border-default bg-surface p-3"
    >
      <div className="flex h-40 items-end gap-2" role="img" aria-label={chart.consistency}>
        {rows.slice(0, 20).map((row, index) => {
          const value = Number(row[columns.at(-1) ?? '']);
          return (
            <div
              key={index}
              className="flex min-w-10 flex-1 flex-col items-center justify-end gap-1"
            >
              <span className="text-micro text-fg-muted">
                {Number.isFinite(value) ? value.toLocaleString() : '—'}
              </span>
              <span
                className="w-full rounded-t bg-accent"
                style={{ height: `${Math.max(3, (Math.abs(value) / maximum) * 110)}px` }}
              />
              <span className="max-w-full truncate text-micro">
                {displayValue(row[columns[0]])}
              </span>
            </div>
          );
        })}
      </div>
      <figcaption className="mt-2 flex items-center gap-2 text-micro text-fg-muted">
        <Badge variant="success">validated</Badge>
        {chart.consistency}
      </figcaption>
    </figure>
  );
}

function DatasetCard({
  candidate,
  onSelect,
  busy,
}: {
  candidate: DataQaCandidate;
  onSelect: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation('dataqa');
  return (
    <Card className="min-w-0">
      <CardHeader>
        <h2 className="flex items-center gap-2 text-h3 font-semibold text-fg-primary">
          <Database className="size-4" aria-hidden />
          {candidate.name}
        </h2>
        <CardDescription>{candidate.relative_path}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Badge variant="neutral">{candidate.format}</Badge>
          <Badge variant="neutral">
            {candidate.row_count?.toLocaleString() ?? '?'} {t('rows')}
          </Badge>
          <Badge variant="success">{Math.round(candidate.score * 100)}%</Badge>
        </div>
        <p className="text-caption text-fg-muted">{candidate.reasons.join(' · ')}</p>
        <p className="line-clamp-2 text-micro text-fg-secondary">{candidate.columns.join(' · ')}</p>
        <Button onClick={onSelect} disabled={busy || !candidate.loadable}>
          {t('useDataset')}
        </Button>
      </CardContent>
    </Card>
  );
}

export default function DataQaRoute() {
  const { t } = useTranslation('dataqa');
  const [source, setSource] = useState('');
  const [discoveryQuery, setDiscoveryQuery] = useState('sales revenue region');
  const [candidates, setCandidates] = useState<DataQaCandidate[]>([]);
  const [session, setSession] = useState<DataQaSession | null>(null);
  const [question, setQuestion] = useState('What is the average revenue by region?');
  const [answer, setAnswer] = useState<DataQaFinalAnswer | null>(null);
  const [streamed, setStreamed] = useState('');
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const askController = useRef<AbortController | null>(null);

  const discover = async () => {
    setBusy(true);
    setError(null);
    try {
      setCandidates((await discoverDataQa(discoveryQuery, source || undefined)).candidates);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    let active = true;
    void discoverDataQa('sales revenue region')
      .then((result) => {
        if (active) setCandidates(result.candidates);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      askController.current?.abort();
    };
  }, []);

  const select = async (candidate: DataQaCandidate) => {
    setBusy(true);
    setError(null);
    try {
      setSession(
        await createDataQaSession(source || undefined, candidate.name, candidate.dataset_id),
      );
      setAnswer(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const ask = async () => {
    if (!session || !question.trim()) return;
    const controller = new AbortController();
    askController.current?.abort();
    askController.current = controller;
    setBusy(true);
    setAsking(true);
    setError(null);
    setStreamed('');
    try {
      const result = await askDataQa(
        session.session_id,
        question.trim(),
        (chunk) => {
          if (typeof chunk.token === 'string') setStreamed((current) => current + chunk.token);
        },
        { timeoutMs: 15_000, signal: controller.signal },
      );
      setAnswer(result.final_answer);
    } catch (reason) {
      setError(
        controller.signal.aborted
          ? t('cancelled')
          : reason instanceof Error
            ? reason.message
            : String(reason),
      );
    } finally {
      if (askController.current === controller) {
        askController.current = null;
        setAsking(false);
        setBusy(false);
      }
    }
  };
  const cancelAsk = () => {
    askController.current?.abort();
    setStreamed('');
  };
  const reset = async () => {
    if (!session) return;
    await resetDataQa(session.session_id);
    setAnswer(null);
    setStreamed('');
  };
  const profile = session?.profile;
  const status = useMemo(() => answer?.status ?? null, [answer]);

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-labelledby="dataqa-title">
      <header>
        <h1 id="dataqa-title" className="text-h2 font-semibold">
          {t('title')}
        </h1>
        <p className="text-body text-fg-muted">{t('subtitle')}</p>
      </header>
      <Card>
        <CardHeader>
          <h2 className="text-h3 font-semibold text-fg-primary">{t('discoverTitle')}</h2>
          <CardDescription>{t('discoverDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <Input
            label={t('sourceLabel')}
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder={t('sourcePlaceholder')}
          />
          <Input
            label={t('discoveryQuestion')}
            value={discoveryQuery}
            onChange={(event) => setDiscoveryQuery(event.target.value)}
            leading={<Search />}
          />
          <Button className="self-end" onClick={() => void discover()} disabled={busy}>
            {t('discover')}
          </Button>
        </CardContent>
      </Card>
      {!session && (
        <section className="grid gap-3 lg:grid-cols-3" aria-label={t('results')}>
          {candidates.map((candidate) => (
            <DatasetCard
              key={candidate.dataset_id}
              candidate={candidate}
              onSelect={() => void select(candidate)}
              busy={busy}
            />
          ))}
        </section>
      )}
      {session && profile && (
        <div className="grid gap-4 xl:grid-cols-[minmax(260px,0.35fr)_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <h2 className="text-h3 font-semibold text-fg-primary">{profile.name}</h2>
              <CardDescription>
                {t('schemaSummary', {
                  rows: profile.row_count.toLocaleString(),
                  columns: profile.columns.length.toLocaleString(),
                })}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2">
                {profile.columns.map((column) => (
                  <div key={column.name} className="rounded border border-border-default p-2">
                    <dt className="font-mono text-caption font-semibold">{column.name}</dt>
                    <dd className="text-micro text-fg-muted">
                      {column.dtype} · {column.null_count} {t('nulls')} · {column.unique_count}{' '}
                      {t('unique')}
                    </dd>
                    {(column.minimum !== undefined || column.maximum !== undefined) && (
                      <dd className="text-micro text-fg-muted">
                        {t('range')}: {displayValue(column.minimum)} –{' '}
                        {displayValue(column.maximum)}
                      </dd>
                    )}
                    {!!column.top_values?.length && column.role === 'category' && (
                      <dd className="truncate text-micro text-fg-muted">
                        {t('categories')}:{' '}
                        {column.top_values
                          .slice(0, 3)
                          .map((item) => displayValue(item.value))
                          .join(' · ')}
                      </dd>
                    )}
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
          <section className="flex min-w-0 flex-col gap-4" aria-label={t('askTitle')}>
            <Card>
              <CardHeader>
                <h2 className="text-h3 font-semibold text-fg-primary">{t('askTitle')}</h2>
                <CardDescription>{t('statefulHint')}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <Textarea
                  label={t('questionLabel')}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  rows={3}
                />
                <div className="flex gap-2">
                  <Button onClick={() => void ask()} disabled={asking}>
                    <Send aria-hidden />
                    {t('ask')}
                  </Button>
                  {asking && (
                    <Button variant="secondary" onClick={cancelAsk}>
                      {t('cancel')}
                    </Button>
                  )}
                  <Button variant="secondary" onClick={() => void reset()} disabled={busy}>
                    <RotateCcw aria-hidden />
                    {t('reset')}
                  </Button>
                </div>
                {busy && streamed && (
                  <p aria-live="polite" className="text-body">
                    {t('answer')}: {streamed}
                  </p>
                )}
              </CardContent>
            </Card>
            {error && (
              <p
                role="alert"
                className="rounded-lg border border-danger-fg p-3 text-body text-danger-fg"
              >
                {error}
              </p>
            )}
            {answer && (
              <Card>
                <CardHeader>
                  <h2 className="flex items-center gap-2 text-h3 font-semibold text-fg-primary">
                    <BarChart3 className="size-5" aria-hidden />
                    {t('answer')}{' '}
                    {status && (
                      <Badge variant={status === 'ok' ? 'success' : 'warning'}>{status}</Badge>
                    )}
                  </h2>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <p aria-live="polite" className="text-body font-medium">
                    {answer.answer}
                  </p>
                  <EvidenceChart answer={answer} />
                  <EvidenceTable answer={answer} />
                  <details>
                    <summary className="cursor-pointer text-caption font-semibold">
                      {t('audit')}
                    </summary>
                    <pre className="mt-2 overflow-x-auto rounded bg-surface-2 p-3 text-micro">
                      <code>{answer.generated_code}</code>
                    </pre>
                  </details>
                  {answer.warnings.map((warning) => (
                    <p key={warning} className="text-micro text-warning-fg">
                      {warning}
                    </p>
                  ))}
                </CardContent>
              </Card>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
