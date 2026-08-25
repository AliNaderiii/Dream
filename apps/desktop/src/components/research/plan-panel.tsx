/**
 * Plan approval panel — human-in-the-loop checkpoint.
 *
 * Shows the generated research plan (questions, hypotheses, methodology,
 * outline tree) with Approve / Modify / Cancel. On Modify, opens an inline
 * editor for the plan fields.
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
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { researchApprove, researchModifyPlan, researchStart } from '@/lib/bridge/research';
import { useBridge } from '@/lib/bridge/hooks';
import type { ResearchOutlineNode, ResearchPlan } from '@/lib/bridge/research-types';
import { useResearchStore } from '@/stores/research-store';
import { cn } from '@/utils/cn';

function OutlineTree({ nodes, depth = 0 }: { nodes: ResearchOutlineNode[]; depth?: number }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  const toggle = (index: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  return (
    <ul className={cn('flex flex-col gap-1', depth > 0 && 'ps-4')} role="tree">
      {nodes.map((node, i) => {
        const hasChildren = node.children && node.children.length > 0;
        const isOpen = expanded.has(i);
        return (
          <li
            key={`${depth}-${i}`}
            role="treeitem"
            aria-expanded={hasChildren ? isOpen : undefined}
          >
            <div className="flex items-center gap-1.5">
              {hasChildren ? (
                <button
                  type="button"
                  onClick={() => toggle(i)}
                  className="shrink-0 text-fg-muted hover:text-fg-primary"
                  aria-label={isOpen ? 'Collapse' : 'Expand'}
                >
                  {isOpen ? (
                    <ChevronDown className="size-3.5" aria-hidden />
                  ) : (
                    <ChevronRight className="size-3.5" aria-hidden />
                  )}
                </button>
              ) : (
                <span className="size-3.5 shrink-0" />
              )}
              <span className="text-caption">{node.title}</span>
            </div>
            {hasChildren && isOpen && <OutlineTree nodes={node.children!} depth={depth + 1} />}
          </li>
        );
      })}
    </ul>
  );
}

function PlanEditor({
  plan,
  onSave,
  onCancel,
}: {
  plan: ResearchPlan;
  onSave: (plan: ResearchPlan) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation('research');
  const [questions, setQuestions] = useState(plan.research_questions.join('\n'));
  const [hypotheses, setHypotheses] = useState(plan.hypotheses.join('\n'));
  const [methodology, setMethodology] = useState(plan.methodology);

  const handleSave = () => {
    onSave({
      ...plan,
      research_questions: questions.split('\n').filter(Boolean),
      hypotheses: hypotheses.split('\n').filter(Boolean),
      methodology,
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
          placeholder={t('plan.onePerLine')}
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
          placeholder={t('plan.onePerLine')}
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
  const { activeSession, upsertSession, setView } = useResearchStore();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const session = activeSession();

  // Auto-fetch plan when the session is in planning state
  useEffect(() => {
    if (!session) return;
    if (session.status === 'planning' && !session.plan) {
      // Trigger plan generation via echo
      researchStart(client, session.session_id)
        .then((updated) => upsertSession(updated))
        .catch((err) => setError(err instanceof Error ? err.message : String(err)));
    }
  }, [session, client, upsertSession]);

  const handleApprove = useCallback(() => {
    if (!session || busy) return;
    setBusy(true);
    setError(null);
    researchApprove(client, session.session_id)
      .then((updated) => {
        upsertSession(updated);
        setView('trace');
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setBusy(false);
      });
  }, [session, client, upsertSession, setView, busy]);

  const handleModify = useCallback(
    (plan: ResearchPlan) => {
      if (!session || busy) return;
      setBusy(true);
      setError(null);
      researchModifyPlan(client, {
        session_id: session.session_id,
        plan,
      })
        .then((updated) => {
          upsertSession(updated);
          setEditing(false);
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          setBusy(false);
        });
    },
    [session, client, upsertSession, busy],
  );

  if (!session) {
    return (
      <div className="flex items-center justify-center p-8 text-body text-fg-muted">
        {t('noActiveSession')}
      </div>
    );
  }

  const plan = session.plan;

  if (!plan) {
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
        <h3 className="text-body font-semibold">{session.topic}</h3>
      </div>

      {/* Header with topic & objective */}
      <div className="rounded-lg border border-border-default bg-surface p-4">
        <h4 className="text-caption font-semibold text-fg-muted">{t('plan.topic')}</h4>
        <p className="mt-1 text-body">{session.topic}</p>
        <h4 className="mt-3 text-caption font-semibold text-fg-muted">{t('plan.objective')}</h4>
        <p className="mt-1 text-caption text-fg-secondary">{session.objective}</p>
      </div>

      {editing ? (
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
              {plan.research_questions.map((q, i) => (
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

          {/* Outline */}
          <section className="rounded-lg border border-border-default bg-surface p-4">
            <h4 className="mb-2 flex items-center gap-2 text-caption font-semibold">
              <ListTree className="size-4 text-accent" aria-hidden />
              {t('plan.outline')}
            </h4>
            <OutlineTree nodes={plan.outline} />
          </section>

          {/* Cost estimate from plan */}
          {plan.estimated_cost_usd !== undefined && (
            <div className="flex items-center gap-4 rounded-md bg-surface-2 px-4 py-2 text-micro">
              <span className="text-fg-muted">{t('estimatedCost')}:</span>
              <span className="font-semibold">${plan.estimated_cost_usd.toFixed(2)}</span>
              <span className="text-fg-muted">·</span>
              <span className="text-fg-muted">{t('tokens')}:</span>
              <span className="font-semibold">
                {((plan.estimated_tokens ?? 0) / 1000).toFixed(0)}k
              </span>
            </div>
          )}
        </>
      )}

      {/* Error */}
      {error && (
        <p role="alert" className="rounded-md bg-danger-bg p-2.5 text-caption text-danger-fg">
          {error}
        </p>
      )}

      {/* Action buttons */}
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
