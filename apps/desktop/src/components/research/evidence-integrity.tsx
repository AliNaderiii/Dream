/**
 * Evidence integrity view — shows each Finding (claim + evidence) from
 * the P1 session record. Links claims to their source section and iteration.
 */

import { ChevronDown, ChevronRight, Link2, Scale } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import type { Finding } from '@/lib/bridge/research-types';

function FindingCard({ finding, index }: { finding: Finding; index: number }) {
  const { t } = useTranslation('research');
  const [expanded, setExpanded] = useState(false);

  const kindVariant =
    finding.kind === 'recommendation'
      ? 'accent'
      : finding.kind === 'anomaly'
        ? 'warning'
        : finding.kind === 'root_cause'
          ? 'danger'
          : 'neutral';

  return (
    <div className="rounded-lg border border-border-default bg-surface" role="article">
      <button
        type="button"
        className="flex w-full items-start gap-3 p-3 text-start"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-micro font-bold text-accent-text">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-caption font-semibold">{finding.claim}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Badge variant={kindVariant}>{finding.kind}</Badge>
            {finding.metric && (
              <span className="text-micro text-fg-muted">
                {finding.metric}: {String(finding.value)}
              </span>
            )}
            {finding.grounded ? (
              <Badge variant="success">{t('integrity.grounded')}</Badge>
            ) : (
              <Badge variant="warning">{t('integrity.ungrounded')}</Badge>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronDown className="size-4 shrink-0 text-fg-muted" aria-hidden />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-fg-muted" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="flex flex-col gap-2 border-t border-border-default px-3 pb-3 pt-2">
          <div className="flex flex-col gap-1.5 rounded-md border border-border-default bg-surface-2 p-2.5">
            <div className="flex items-start gap-2">
              <Link2 className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-micro font-semibold">{t('integrity.evidence')}</span>
                  {finding.section_id && <Badge variant="neutral">{finding.section_id}</Badge>}
                  <span className="text-micro text-fg-muted">iter {finding.iteration}</span>
                </div>
                <p className="mt-0.5 text-micro text-fg-secondary">{finding.evidence}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function EvidenceIntegrity({ findings }: { findings: Finding[] }) {
  const { t } = useTranslation('research');

  if (findings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <Scale className="size-8 text-fg-muted" aria-hidden />
        <p className="text-body text-fg-muted">{t('integrity.noClaims')}</p>
      </div>
    );
  }

  const grounded = findings.filter((f) => f.grounded).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4 rounded-lg border border-border-default bg-surface p-4">
        <Scale className="size-6 text-accent" aria-hidden />
        <div>
          <h4 className="text-caption font-semibold">{t('integrity.summary')}</h4>
          <p className="text-micro text-fg-muted">
            {t('integrity.summaryDetail', { claims: findings.length, evidence: grounded })}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2" role="list" aria-label={t('integrity.claims')}>
        {findings.map((finding, index) => (
          <FindingCard
            key={`${finding.section_id}-${finding.iteration}-${index}`}
            finding={finding}
            index={index}
          />
        ))}
      </div>
    </div>
  );
}
