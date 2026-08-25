/**
 * Plan approval panel — human-in-the-loop checkpoint.
 *
 * Shows the P1 plan shape: questions, hypotheses, methodology, sections
 * (each with section_id, title, thesis, questions). Approve / Modify / Cancel.
 */

import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Edit3,
  HelpCircle,
  Lightbulb,
  ListTree,
  Microscope,
  X,
} from 'lucide-react';
import { useCallback, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import {
  researchApprove,
  researchGet,
  researchModify,
  researchStart,
  mapResearchError,
} from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { Plan, Section } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

function SectionOutline({ section, depth = 0 }: { section: Section; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasDetails = section.questions.length > 0 || section.thesis;

  return (
    <li className={cn('flex flex-col gap-1', depth > 0 && 'ps-4')} role="treeitem">
      <div className="flex items-center gap-1.5">
        {hasDetails ? (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 text-fg-muted hover:text-fg-primary"
          >
            {expanded ? (
              <ChevronDown className="size-3.5" aria-hidden />
            ) : (
              <ChevronRight className="size-3.5" aria-hidden />
            )}
          </button>
        ) : (
          <span className="size-3.5 shrink-0" />
        )}
        <span className="text-caption font-semibold">{section.title}</span>
        {section.status !== 'PENDING' && (
          <span className="text-micro text-fg-muted">({section.status})</span>
        )}
      </div>
      {expanded && hasDetails && (
        <div className="flex flex-col gap-1 ps-5">
          {section.thesis && (
            <p className="text-micro text-fg-secondary italic">{section.thesis}</p>
          )}
          {section.questions.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {section.questions.map((q, i) => (
                <li key={i} className="text-micro text-fg-muted">
                  • {q}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function PlanEditor({
  plan,
  onSave,
  onCancel,
}: {
  plan: Plan;
  onSave: (changes: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation('research');
  const [questions, setQuestions] = useState(plan.questions.join('\n'));
  const [hypotheses, setHypotheses] = useState(plan.hypotheses.join('\n'));
  const [methodology, setMethodology] = useState(plan.methodology);

  const handleSave = () => {
    onSave({
      sections: plan.sections.map((s) => ({
        section_id: s.section_id,
        title: s.title,
        thesis: s.thesis,
      })),
      _questions: questions.split('\n').filter(Boolean),
      _hypotheses: hypotheses.split('\n').filter(Boolean),
      _methodology: methodology,
    });
  };

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-accent bg-accent-soft/30 p-4"
      role="dialog"
      aria-label={t('plan.editPlan')}
    >
      <fieldset className="flex flex-col gap-1.5">
        <label htmlFor="plan-questions" className="text-caption font-semibold">
          {t('plan.researchQuestions')}
        </label>
        <textarea
          id="plan-questions"
          value={questions}
          onChange={(e) => setQuestions(e.target.value)}
          rows={4}
          className="rounded-md border border-border-default bg-surface px-3 py-2 text-caption outline-none focus:border-accent ltr-island"
        />
      </fieldset>
      <fieldset className="flex flex-col gap-1.5">
        <label htmlFor="plan-hypotheses" className="text-caption font-semibold">
          {t('plan.hypotheses')}
        </label>
        <textarea
          id="plan-hypotheses"
          value={hypotheses}
          onChange={(e) => setHypotheses(e.target.value)}
          rows={3}
          className="rounded-md border border-border-default bg-surface px-3 py-2 text-caption outline-none focus:border-accent ltr-island"
        />
      </fieldset>
      <fieldset className="flex flex-col gap-1.5">
        <label htmlFor="plan-methodology" className="text-caption font-semibold">
          {t('plan.methodology')}
        </label>
        <textarea
          id="plan-methodology"
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          rows={4}
          className="rounded-md border border-border-default bg-surface px-3 py-2 text-caption outline-none focus:border-accent ltr-island"
        />
      </fieldset>
      <div className="flex items-center gap-2">
        <Button variant="primary" size="sm" onClick={handleSave}>
          {t('plan.saveChanges')}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t('cancel')}
        </Button>
      </div>
    </div>
  );
}

export function PlanPanel() {
  const { t } = useTranslation('research');
  const { client } = useBridge();
  const { activeRecord, setActiveRecord, upsertSession, setView } = useResearchStore();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const plan = activeRecord?.plan;
  const costEstimate = activeRecord?.cost_estimate;

  const handleApprove = useCallback(() => {
    if (!activeRecord || busy) return;
    setBusy(true);
    setError(null);
    researchApprove(client, activeRecord.session_id)
      .then((result) => {
        upsertSession(result);
        // Now start execution
        return researchStart(client, activeRecord.session_id);
      })
      .then((summary) => {
        upsertSession(summary);
        // Refresh the record
        return researchGet(client, activeRecord.session_id);
      })
      .then((record) => {
        setActiveRecord(record);
        setView('trace');
      })
      .catch((err: unknown) => {
        const mapped = mapResearchError(err);
        setError(mapped.fallback);
      })
      .finally(() => setBusy(false));
  }, [activeRecord, client, upsertSession, setActiveRecord, setView, busy]);

  const handleModify = useCallback(
    (changes: Record<string, unknown>) => {
      if (!activeRecord || busy) return;
      setBusy(true);
      setError(null);
      researchModify(client, { session_id: activeRecord.session_id, changes })
        .then((result) => {
          upsertSession(result);
          return researchGet(client, activeRecord.session_id);
        })
        .then((record) => {
          setActiveRecord(record);
          setEditing(false);
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => setBusy(false));
    },
    [activeRecord, client, upsertSession, setActiveRecord, busy],
  );

  if (!activeRecord) {
    return (
      <div className="flex items-center justify-center p-8 text-body text-fg-muted">
        {t('noActiveSession')}
      </div>
    );
  }

  if (!plan || plan.sections.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 p-8"
        role="status"
        aria-live="polite"
      >
        <Microscope
          className="size-8 animate-pulse text-accent motion-reduce:animate-none"
          aria-hidden
        />
        <p className="text-body text-fg-muted">{t('plan.generating')}</p>
      </div>
    );
  }

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
        <h3 className="text-body font-semibold">{activeRecord.topic}</h3>
      </div>

      {/* Topic & workspace */}
      <div className="rounded-lg border border-border-default bg-surface p-4">
        <h4 className="text-caption font-semibold text-fg-muted">{t('plan.topic')}</h4>
        <p className="mt-1 text-body">{activeRecord.topic}</p>
        <h4 className="mt-3 text-caption font-semibold text-fg-muted">{t('plan.workspace')}</h4>
        <p className="mt-1 text-caption text-fg-secondary font-mono">{activeRecord.workspace}</p>
      </div>

      {editing && plan ? (
        <PlanEditor plan={plan} onSave={handleModify} onCancel={() => setEditing(false)} />
      ) : (
        <>
          {/* Research Questions */}
          <section className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-2 flex items-center gap-2 text-caption font-semibold">
              <HelpCircle className="size-4 text-accent" aria-hidden />
              {t('plan.researchQuestions')}
            </h4>
            <ol className="list-inside list-decimal flex flex-col gap-1">
              {plan.questions.map((q, i) => (
                <li key={i} className="text-caption text-fg-secondary">
                  {q}
                </li>
              ))}
            </ol>
          </section>

          {/* Hypotheses */}
          <section className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-2 flex items-center gap-2 text-caption font-semibold">
              <Lightbulb className="size-4 text-warning-fg" aria-hidden />
              {t('plan.hypotheses')}
            </h4>
            <ul className="flex flex-col gap-1">
              {plan.hypotheses.map((h, i) => (
                <li key={i} className="text-caption text-fg-secondary">
                  • {h}
                </li>
              ))}
            </ul>
          </section>

          {/* Methodology */}
          <section className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-2 text-caption font-semibold">{t('plan.methodology')}</h4>
            <p className="text-caption text-fg-secondary">{plan.methodology}</p>
          </section>

          {/* Sections outline */}
          <section className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-2 flex items-center gap-2 text-caption font-semibold">
              <ListTree className="size-4 text-accent" aria-hidden />
              {t('plan.sections')} ({plan.sections.length})
            </h4>
            <ul className="flex flex-col gap-2" role="tree">
              {plan.sections.map((section) => (
                <SectionOutline key={section.section_id} section={section} />
              ))}
            </ul>
          </section>

          {/* Cost estimate from plan */}
          {costEstimate && costEstimate.estimated_tokens > 0 && (
            <div className="flex items-center gap-4 rounded-md bg-surface-2 px-4 py-2 text-micro">
              <span className="text-fg-muted">{t('estimatedCost')}:</span>
              <span className="font-semibold">{costEstimate.estimated_model_calls} calls</span>
              <span className="text-fg-muted">·</span>
              <span className="text-fg-muted">{t('tokens')}:</span>
              <span className="font-semibold">
                {(costEstimate.estimated_tokens / 1000).toFixed(0)}k
              </span>
              <span className="text-fg-muted">·</span>
              <span className="text-fg-muted">{t('duration')}:</span>
              <span className="font-semibold">
                ~{Math.round(costEstimate.max_wall_clock_seconds / 60)}m
              </span>
            </div>
          )}
        </>
      )}

      {error && (
        <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
          {error}
        </p>
      )}

      {!editing && (
        <div
          className="flex items-center gap-3 border-t border-border-default pt-4"
          role="group"
          aria-label={t('plan.actions')}
        >
          <Button
            variant="primary"
            size="md"
            onClick={handleApprove}
            disabled={busy}
            aria-label={t('plan.approve')}
          >
            <CheckCircle2 aria-hidden />
            {t('plan.approve')}
          </Button>
          <Button
            variant="ghost"
            size="md"
            onClick={() => setEditing(true)}
            disabled={busy}
            aria-label={t('plan.modify')}
          >
            <Edit3 aria-hidden />
            {t('plan.modify')}
          </Button>
          <Button
            variant="ghost"
            size="md"
            onClick={() => setView('list')}
            aria-label={t('cancel')}
          >
            <X aria-hidden />
            {t('cancel')}
          </Button>
        </div>
      )}
    </div>
  );
}
