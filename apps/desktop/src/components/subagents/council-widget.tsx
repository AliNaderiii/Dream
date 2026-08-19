/**
 * Council widget — the three-role review (proposer / critic / judge).
 *
 * Rendered in place of the plain subagent detail when the selected child
 * belongs to a council pipeline. One column per role shows the provider,
 * the local-vs-leaves-machine privacy badge, the live status, and the
 * result excerpt; the winner strip appears once the judge completes.
 * `council.get` is polled while any member is still running, mirroring the
 * page's `subagent.list` polling.
 */

import { Lightbulb, Scale, ShieldAlert } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { SubagentStatusBadge } from '@/components/subagents/status-badge';
import { Badge } from '@/components/ui/badge';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';
import type { CouncilDto, CouncilMemberDto } from '@/lib/bridge/types';
import { isTerminalStatus } from '@/lib/bridge/types';

/** How often to refresh the council while a member is still running. */
const POLL_MS = 500;

const ROLE_ICONS = {
  proposer: Lightbulb,
  critic: ShieldAlert,
  judge: Scale,
} as const;

function CouncilColumn({ member, roleLabel }: { member: CouncilMemberDto; roleLabel: string }) {
  const { t } = useTranslation('subagents');
  const Icon = ROLE_ICONS[member.role];
  const excerpt = member.result ? member.result.replace(/\s+/g, ' ').trim() : null;
  return (
    <section
      aria-label={roleLabel}
      className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3"
    >
      <header className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-body font-semibold">
          <Icon className="size-4 text-fg-secondary" aria-hidden />
          {roleLabel}
        </span>
        <SubagentStatusBadge status={member.status} />
      </header>
      <p className="text-micro text-fg-muted">
        {member.provider}
        {member.model ? ` · ${member.model}` : ''}
      </p>
      <div className="flex flex-wrap gap-1.5">
        <Badge variant={member.leaves_machine ? 'warning' : 'success'}>
          {member.leaves_machine ? t('leavesMachine') : t('leavesLocal')}
        </Badge>
      </div>
      <p className="line-clamp-4 text-caption text-fg-secondary">{excerpt ?? '\u2014'}</p>
    </section>
  );
}

export function CouncilWidget({ councilId }: { councilId: string }) {
  const { t } = useTranslation('subagents');
  const { call } = useBridge();
  const [council, setCouncil] = useState<CouncilDto | null>(null);
  const liveRef = useRef(true);

  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const result = await call<CouncilDto>('council.get', { council_id: councilId });
      if (liveRef.current) setCouncil(result);
    } catch {
      // Keep the last snapshot; hard failures surface in the page's banner.
    }
  }, [call, councilId]);

  useEffect(() => {
    let current = true;
    const run = async () => {
      try {
        const result = await call<CouncilDto>('council.get', { council_id: councilId });
        if (current) setCouncil(result);
      } catch {
        // Keep the last snapshot; hard failures surface in the page's banner.
      }
    };
    void run();
    return () => {
      current = false;
    };
  }, [call, councilId]);

  const anyRunning = council?.members.some((m) => !isTerminalStatus(m.status)) ?? false;
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [anyRunning, load]);

  if (!council) {
    return <p className="text-body text-fg-secondary">{t('selectPrompt')}</p>;
  }
  if (council.refusal) {
    return (
      <p
        role="alert"
        className="rounded-lg border border-danger-fg/30 bg-danger-bg p-3 text-caption text-danger-fg"
      >
        {council.refusal}
      </p>
    );
  }

  const roleLabels: Record<CouncilMemberDto['role'], string> = {
    proposer: t('roleProposer'),
    critic: t('roleCritic'),
    judge: t('roleJudge'),
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {council.members.map((member) => (
          <CouncilColumn key={member.role} member={member} roleLabel={roleLabels[member.role]} />
        ))}
      </div>
      <footer
        aria-label={t('councilWinner')}
        className="rounded-lg border border-accent bg-accent-soft p-3"
      >
        {council.winner ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-caption font-semibold text-accent-text">{t('winner')}</span>
            <p className="line-clamp-6 whitespace-pre-line text-body">{council.winner}</p>
            <p className="text-micro text-fg-muted">{council.sentence_en}</p>
            <p className="text-micro text-fg-muted">{council.sentence_fa}</p>
          </div>
        ) : (
          <p className="text-caption text-fg-secondary">{t('councilRunning')}</p>
        )}
      </footer>
    </div>
  );
}
