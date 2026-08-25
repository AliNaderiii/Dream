/**
 * Evidence integrity view — shows each key claim linked to the run/code that
 * produced it (statistics-integrity skill). The "claims ⇅ evidence" panel
 * that makes Dream's analysis trustworthy and auditable.
 */

import { ChevronDown, ChevronRight, Code2, Link2, Scale } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';
import { redactSecrets } from '@/lib/bridge/research';
import type { ResearchClaim, ResearchEvidence } from '@/lib/bridge/research-types';

function EvidenceRow({ evidence }: { evidence: ResearchEvidence }) {
  const { t } = useTranslation('research');
  const [showCode, setShowCode] = useState(false);

  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border-default bg-surface-2 p-2.5">
      <div className="flex items-start gap-2">
        <Link2 className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-micro font-semibold">{evidence.source}</span>
            {evidence.step_id && <Badge variant="neutral">{evidence.step_id}</Badge>}
          </div>
          <p className="mt-0.5 text-micro text-fg-secondary">{evidence.value}</p>
        </div>
      </div>
      {evidence.code_snippet && (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-micro text-fg-muted hover:text-fg-primary"
            onClick={() => setShowCode(!showCode)}
            aria-expanded={showCode}
          >
            <Code2 className="size-3" aria-hidden />
            {showCode ? t('integrity.hideCode') : t('integrity.showCode')}
            {showCode ? (
              <ChevronDown className="size-3" aria-hidden />
            ) : (
              <ChevronRight className="size-3" aria-hidden />
            )}
          </button>
          {showCode && (
            <pre className="mt-1 overflow-x-auto rounded bg-surface px-2 py-1.5 font-mono text-micro whitespace-pre-wrap">
              {redactSecrets(evidence.code_snippet)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ClaimCard({ claim, index }: { claim: ResearchClaim; index: number }) {
  const { t } = useTranslation('research');
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-lg border border-border-default bg-surface"
      role="article"
      aria-label={t('integrity.claim', { index: index + 1 })}
    >
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
          <p className="text-caption font-semibold">{claim.text}</p>
          <p className="mt-1 text-micro text-fg-muted">
            {t('integrity.evidenceCount', { count: claim.evidence.length })}
          </p>
        </div>
        {expanded ? (
          <ChevronDown className="size-4 shrink-0 text-fg-muted" aria-hidden />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-fg-muted" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="flex flex-col gap-2 border-t border-border-default px-3 pb-3 pt-2">
          {claim.evidence.map((evidence) => (
            <EvidenceRow key={evidence.evidence_id} evidence={evidence} />
          ))}
        </div>
      )}
    </div>
  );
}

export function EvidenceIntegrity({ claims }: { claims: ResearchClaim[] }) {
  const { t } = useTranslation('research');

  if (claims.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-8">
        <Scale className="size-8 text-fg-muted" aria-hidden />
        <p className="text-body text-fg-muted">{t('integrity.noClaims')}</p>
      </div>
    );
  }

  const totalEvidence = claims.reduce((sum, c) => sum + c.evidence.length, 0);

  return (
    <div className="flex flex-col gap-4">
      {/* Summary */}
      <div className="flex items-center gap-4 rounded-lg border border-border-default bg-surface p-4">
        <Scale className="size-6 text-accent" aria-hidden />
        <div>
          <h4 className="text-caption font-semibold">{t('integrity.summary')}</h4>
          <p className="text-micro text-fg-muted">
            {t('integrity.summaryDetail', {
              claims: claims.length,
              evidence: totalEvidence,
            })}
          </p>
        </div>
      </div>

      {/* Claims list */}
      <div className="flex flex-col gap-2" role="list" aria-label={t('integrity.claims')}>
        {claims.map((claim, index) => (
          <ClaimCard key={claim.claim_id} claim={claim} index={index} />
        ))}
      </div>
    </div>
  );
}
