/**
 * New research composer — topic, objective, data sources, depth, and
 * model/route picker. Shows a cost estimate before start and surfaces the
 * privacy sentence ("does data leave the machine?") for the selected route.
 */

import { AlertTriangle, Database, Globe, Lock, Sparkles, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import {
  researchCreate,
  researchEstimate,
  researchStart,
  validateResearchCreate,
} from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type {
  ResearchCostEstimate,
  ResearchCreateParams,
  ResearchDataSource,
  ResearchDepth,
} from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

const MODEL_ROUTES = [
  {
    id: 'local-ollama',
    label: 'Local (Ollama)',
    description: 'Never leaves this machine',
    leavesMachine: false,
  },
  {
    id: 'local-transformers',
    label: 'Local (Transformers)',
    description: 'Never leaves this machine',
    leavesMachine: false,
  },
  {
    id: 'aval-ai',
    label: 'Aval AI',
    description: 'Prompts leave this machine to api.avalai.ir',
    leavesMachine: true,
  },
  {
    id: 'openai',
    label: 'OpenAI',
    description: 'Prompts leave this machine to api.openai.com',
    leavesMachine: true,
  },
];

function CostEstimatePanel({ estimate }: { estimate: ResearchCostEstimate }) {
  const { t } = useTranslation('research');
  return (
    <div className="rounded-lg border border-border-default bg-surface-2 p-3">
      <h4 className="text-caption font-semibold">{t('costEstimate')}</h4>
      <div className="mt-2 grid grid-cols-3 gap-3 text-micro">
        <div>
          <span className="text-fg-muted">{t('tokens')}</span>
          <p className="font-semibold">{(estimate.estimated_tokens / 1000).toFixed(0)}k</p>
        </div>
        <div>
          <span className="text-fg-muted">{t('cost')}</span>
          <p className="font-semibold">${estimate.estimated_cost_usd.toFixed(2)}</p>
        </div>
        <div>
          <span className="text-fg-muted">{t('duration')}</span>
          <p className="font-semibold">~{Math.round(estimate.estimated_duration_seconds / 60)}m</p>
        </div>
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer text-micro text-fg-muted hover:text-fg-secondary">
          {t('breakdown')}
        </summary>
        <div className="mt-2 flex flex-col gap-1">
          {estimate.breaks_down.map((item) => (
            <div key={item.phase} className="flex items-center justify-between text-micro">
              <span className="capitalize text-fg-muted">{item.phase}</span>
              <span>
                {(item.tokens / 1000).toFixed(0)}k · ${item.cost_usd.toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function PrivacySentence({ leavesMachine }: { leavesMachine: boolean }) {
  const { t } = useTranslation('research');
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-md px-3 py-2 text-caption',
        leavesMachine ? 'bg-warning-bg text-warning-fg' : 'bg-success-bg text-success-fg',
      )}
      role="status"
    >
      {leavesMachine ? (
        <>
          <Globe className="size-4 shrink-0" aria-hidden />
          <span>{t('privacy.leavesMachine')}</span>
        </>
      ) : (
        <>
          <Lock className="size-4 shrink-0" aria-hidden />
          <span>{t('privacy.staysLocal')}</span>
        </>
      )}
    </div>
  );
}

function DataSourceRow({ source, onRemove }: { source: ResearchDataSource; onRemove: () => void }) {
  const { t } = useTranslation('research');
  return (
    <li className="flex items-center gap-2 rounded-md border border-border-default bg-surface px-3 py-2">
      <Database className="size-4 shrink-0 text-fg-muted" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-caption">{source.name}</span>
      <Badge variant="neutral">{source.kind}</Badge>
      <button
        type="button"
        onClick={onRemove}
        className="text-fg-muted hover:text-danger-fg"
        aria-label={t('removeSource', { name: source.name })}
      >
        <Trash2 className="size-4" aria-hidden />
      </button>
    </li>
  );
}

export function ResearchComposer() {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { setView, upsertSession, setActiveSession } = useResearchStore();

  const [topic, setTopic] = useState('');
  const [objective, setObjective] = useState('');
  const [depth, setDepth] = useState<ResearchDepth>('deep');
  const [modelRoute, setModelRoute] = useState(MODEL_ROUTES[0].id);
  const [dataSources, setDataSources] = useState<ResearchDataSource[]>([]);
  const [newSourceName, setNewSourceName] = useState('');
  const [estimate, setEstimate] = useState<ResearchCostEstimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRoute = MODEL_ROUTES.find((r) => r.id === modelRoute) ?? MODEL_ROUTES[0];

  const params: ResearchCreateParams = {
    topic,
    objective,
    depth,
    data_sources: dataSources,
    model_route: modelRoute,
  };

  const validationError = validateResearchCreate(params);

  // Estimate cost when params change (debounced)
  useEffect(() => {
    if (validationError) return;
    const timer = setTimeout(() => {
      researchEstimate(client, params)
        .then(setEstimate)
        .catch(() => setEstimate(null));
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic, objective, depth, client]);

  // Clear estimate when validation fails
  if (validationError && estimate !== null) {
    setEstimate(null);
  }

  const addSource = useCallback(() => {
    if (!newSourceName.trim()) return;
    const source: ResearchDataSource = {
      source_id: `src-${Date.now()}`,
      name: newSourceName.trim(),
      kind: 'dataset',
    };
    setDataSources((prev) => [...prev, source]);
    setNewSourceName('');
  }, [newSourceName]);

  const removeSource = useCallback((id: string) => {
    setDataSources((prev) => prev.filter((s) => s.source_id !== id));
  }, []);

  const handleStart = () => {
    if (validationError || busy) return;
    setBusy(true);
    setError(null);

    researchCreate(client, params)
      .then((session) => {
        upsertSession(session);
        setActiveSession(session.session_id);
        return researchStart(client, session.session_id);
      })
      .then((started) => {
        upsertSession(started);
        setView('plan');
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setView('list')}
          className="text-caption text-fg-muted hover:text-fg-primary"
        >
          ← {t('backToList')}
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {/* Topic */}
        <fieldset className="flex flex-col gap-1.5">
          <label htmlFor="research-topic" className="text-caption font-semibold">
            {t('composer.topic')}
          </label>
          <input
            id="research-topic"
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={t('composer.topicPlaceholder')}
            maxLength={500}
            className="h-10 rounded-md border border-border-default bg-surface px-3 text-body outline-none focus:border-accent ltr-island"
          />
        </fieldset>

        {/* Objective */}
        <fieldset className="flex flex-col gap-1.5">
          <label htmlFor="research-objective" className="text-caption font-semibold">
            {t('composer.objective')}
          </label>
          <textarea
            id="research-objective"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder={t('composer.objectivePlaceholder')}
            rows={3}
            maxLength={2000}
            className="rounded-md border border-border-default bg-surface px-3 py-2 text-body outline-none focus:border-accent ltr-island"
          />
        </fieldset>

        {/* Data Sources */}
        <fieldset className="flex flex-col gap-1.5">
          <label className="text-caption font-semibold">{t('composer.dataSources')}</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newSourceName}
              onChange={(e) => setNewSourceName(e.target.value)}
              placeholder={t('composer.addSource')}
              className="h-8 flex-1 rounded-md border border-border-default bg-surface px-2.5 text-caption outline-none focus:border-accent ltr-island"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addSource();
                }
              }}
            />
            <Button variant="ghost" size="sm" onClick={addSource} disabled={!newSourceName.trim()}>
              {t('add')}
            </Button>
          </div>
          {dataSources.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {dataSources.map((source) => (
                <DataSourceRow
                  key={source.source_id}
                  source={source}
                  onRemove={() => removeSource(source.source_id)}
                />
              ))}
            </ul>
          )}
        </fieldset>

        {/* Depth */}
        <fieldset className="flex flex-col gap-1.5">
          <label className="text-caption font-semibold">{t('composer.depth')}</label>
          <div className="flex gap-3" role="radiogroup" aria-label={t('composer.depth')}>
            {(['simple', 'deep'] as const).map((d) => (
              <label
                key={d}
                className={cn(
                  'flex flex-1 cursor-pointer flex-col gap-1 rounded-lg border p-3 transition-colors',
                  depth === d
                    ? 'border-accent bg-accent-soft'
                    : 'border-border-default hover:bg-surface-2',
                )}
              >
                <input
                  type="radio"
                  name="research-depth"
                  value={d}
                  checked={depth === d}
                  onChange={() => setDepth(d)}
                  className="sr-only"
                />
                <span className="flex items-center gap-2 text-caption font-semibold capitalize">
                  <Sparkles className="size-3.5" aria-hidden />
                  {t(`depth.${d}`)}
                </span>
                <span className="text-micro text-fg-muted">{t(`depth.${d}Desc`)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Model Route */}
        <fieldset className="flex flex-col gap-1.5">
          <label htmlFor="research-model" className="text-caption font-semibold">
            {t('composer.modelRoute')}
          </label>
          <select
            id="research-model"
            value={modelRoute}
            onChange={(e) => setModelRoute(e.target.value)}
            className="h-10 rounded-md border border-border-default bg-surface px-3 text-body outline-none focus:border-accent"
          >
            {MODEL_ROUTES.map((route) => (
              <option key={route.id} value={route.id}>
                {route.label}
              </option>
            ))}
          </select>
          <PrivacySentence leavesMachine={selectedRoute.leavesMachine} />
          {selectedRoute.leavesMachine && (
            <p className="flex items-center gap-1.5 text-micro text-warning-fg">
              <AlertTriangle className="size-3.5" aria-hidden />
              {t('composer.privacyWarning')}
            </p>
          )}
        </fieldset>

        {/* Cost Estimate */}
        {estimate && <CostEstimatePanel estimate={estimate} />}

        {/* Error */}
        {error && (
          <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
            {error}
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <Button
            variant="primary"
            size="md"
            onClick={handleStart}
            disabled={!!validationError || busy}
            aria-label={t('composer.start')}
          >
            <Sparkles aria-hidden />
            {busy ? t('composer.starting') : t('composer.start')}
          </Button>
          <Button variant="ghost" size="md" onClick={() => setView('list')}>
            {t('cancel')}
          </Button>
        </div>
      </div>
    </div>
  );
}
