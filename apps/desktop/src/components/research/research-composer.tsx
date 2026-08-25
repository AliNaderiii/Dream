/**
 * New research composer — topic, workspace, depth, and model/route picker.
 *
 * Maps the P1 `research.create` params: { topic, workspace, config? }.
 * Shows cost estimate from the plan response (not a separate RPC).
 * Surfaces the privacy sentence for the selected route.
 */

import { AlertTriangle, FolderOpen, Globe, Lock, Sparkles } from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import {
  researchCreate,
  researchGet,
  researchPlan,
  validateResearchCreate,
} from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { ResearchCreateParams, ResearchConfig } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

const MODEL_ROUTES = [
  { id: 'local', label: 'Local (offline)', leavesMachine: false },
  { id: 'aval-ai', label: 'Aval AI', leavesMachine: true },
  { id: 'openai', label: 'OpenAI', leavesMachine: true },
];

const DEPTH_PRESETS: Record<string, Partial<ResearchConfig>> = {
  brief: { max_iterations: 2, max_sections: 3, output_length: 'brief', max_time_seconds: 300 },
  standard: {
    max_iterations: 3,
    max_sections: 6,
    output_length: 'standard',
    max_time_seconds: 900,
  },
  deep: { max_iterations: 5, max_sections: 10, output_length: 'detailed', max_time_seconds: 1800 },
};

export function ResearchComposer() {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { setView, upsertSession, setActiveSession, setActiveRecord, setActiveSummary } =
    useResearchStore();

  const [topic, setTopic] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [depth, setDepth] = useState<'brief' | 'standard' | 'deep'>('standard');
  const [modelRoute, setModelRoute] = useState(MODEL_ROUTES[0].id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRoute = MODEL_ROUTES.find((r) => r.id === modelRoute) ?? MODEL_ROUTES[0];
  const config = DEPTH_PRESETS[depth];

  const params: ResearchCreateParams = {
    topic,
    workspace,
    config: { ...config, allow_network: selectedRoute.leavesMachine },
  };

  const validationError = validateResearchCreate(params);

  const handleStart = useCallback(() => {
    if (validationError || busy) return;
    setBusy(true);
    setError(null);

    researchCreate(client, params)
      .then((summary) => {
        upsertSession(summary);
        setActiveSession(summary.session_id);
        // Trigger planning
        return researchPlan(client, summary.session_id);
      })
      .then((planResult) => {
        upsertSession(planResult);
        // Fetch the full record for the plan panel
        return researchGet(client, planResult.session_id);
      })
      .then((record) => {
        setActiveRecord(record);
        setActiveSummary(null);
        setView('plan');
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setBusy(false);
      });
  }, [
    validationError,
    busy,
    client,
    params,
    upsertSession,
    setActiveSession,
    setActiveRecord,
    setActiveSummary,
    setView,
  ]);

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

        {/* Workspace */}
        <fieldset className="flex flex-col gap-1.5">
          <label htmlFor="research-workspace" className="text-caption font-semibold">
            {t('composer.workspace')}
          </label>
          <div className="flex items-center gap-2">
            <FolderOpen className="size-4 shrink-0 text-fg-muted" aria-hidden />
            <input
              id="research-workspace"
              type="text"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
              placeholder={t('composer.workspacePlaceholder')}
              className="h-10 flex-1 rounded-md border border-border-default bg-surface px-3 text-body outline-none focus:border-accent ltr-island"
            />
          </div>
          <p className="text-micro text-fg-muted">{t('composer.workspaceHelp')}</p>
        </fieldset>

        {/* Depth */}
        <fieldset className="flex flex-col gap-1.5">
          <label className="text-caption font-semibold">{t('composer.depth')}</label>
          <div className="flex gap-3" role="radiogroup" aria-label={t('composer.depth')}>
            {(['brief', 'standard', 'deep'] as const).map((d) => (
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
          {/* Privacy sentence */}
          <div
            className={cn(
              'flex items-center gap-2 rounded-md px-3 py-2 text-caption',
              selectedRoute.leavesMachine
                ? 'bg-warning-bg text-warning-fg'
                : 'bg-success-bg text-success-fg',
            )}
            role="status"
          >
            {selectedRoute.leavesMachine ? (
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
          {selectedRoute.leavesMachine && (
            <p className="flex items-center gap-1.5 text-micro text-warning-fg">
              <AlertTriangle className="size-3.5" aria-hidden />
              {t('composer.privacyWarning')}
            </p>
          )}
        </fieldset>

        {/* Config summary */}
        {config && (
          <div className="rounded-lg border border-border-default bg-surface-2 p-3">
            <h4 className="text-caption font-semibold">{t('composer.configSummary')}</h4>
            <div className="mt-2 grid grid-cols-3 gap-3 text-micro">
              <div>
                <span className="text-fg-muted">{t('composer.maxSections')}</span>
                <p className="font-semibold">{config.max_sections}</p>
              </div>
              <div>
                <span className="text-fg-muted">{t('composer.maxIterations')}</span>
                <p className="font-semibold">{config.max_iterations}</p>
              </div>
              <div>
                <span className="text-fg-muted">{t('composer.maxTime')}</span>
                <p className="font-semibold">{Math.round((config.max_time_seconds ?? 0) / 60)}m</p>
              </div>
            </div>
          </div>
        )}

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
