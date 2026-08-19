/**
 * Approval dialog for dangerous tool calls (S07).
 *
 * Offers three actions:
 *   1. Allow once — execute this call, ask again next time.
 *   2. Always allow this tool this session — add to the pane's allowlist.
 *   3. Deny — block the call (fail-closed).
 *
 * Copy is bilingual via the locale generator (chat.approval.* keys).
 * The dialog traps focus and is keyboard-navigable (Escape = deny).
 */

import { ShieldAlert } from 'lucide-react';
import type { KeyboardEvent } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import type { ApprovalDecision, PendingApproval } from '@/types';

interface ApprovalDialogProps {
  approval: PendingApproval;
  onDecision: (decision: ApprovalDecision) => void;
}

export function ApprovalDialog({ approval, onDecision }: ApprovalDialogProps) {
  const { t } = useTranslation('chat');

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onDecision('deny');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${t('approval.title')}: ${approval.toolName}`}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/60 p-4"
    >
      <div className="w-full max-w-md rounded-lg border border-border-default bg-canvas p-5 shadow-lg">
        <div className="flex items-start gap-3">
          <ShieldAlert className="size-6 shrink-0 text-warning-fg" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="text-heading font-semibold text-fg-primary">{t('approval.title')}</h2>
            <p className="mt-1 text-caption text-fg-secondary">
              <span className="font-medium text-fg-primary">{approval.toolName}</span>{' '}
              {t('approval.description')}
            </p>
            <pre className="mt-2 max-h-24 overflow-auto rounded-sm bg-surface-2 px-2 py-1.5 text-mono text-micro text-fg-secondary">
              {approval.argsSummary}
            </pre>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2">
          <Button variant="primary" onClick={() => onDecision('allow_once')} className="w-full">
            {t('approval.allowOnce')}
          </Button>
          <Button
            variant="secondary"
            onClick={() => onDecision('allow_always_session')}
            className="w-full"
          >
            {t('approval.alwaysAllow')}
          </Button>
          <Button
            variant="ghost"
            onClick={() => onDecision('deny')}
            className="w-full text-danger-fg"
          >
            {t('approval.deny')}
          </Button>
        </div>
      </div>
    </div>
  );
}
