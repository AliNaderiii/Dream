/** Focus-trapped, fail-closed approval alert for dangerous tool calls. */

import { ShieldAlert } from 'lucide-react';
import { useRef } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslation } from '@/lib/i18n';
import type { ApprovalDecision, PendingApproval } from '@/types';

interface ApprovalDialogProps {
  approval: PendingApproval;
  onDecision: (decision: ApprovalDecision) => void;
}

export function ApprovalDialog({ approval, onDecision }: ApprovalDialogProps) {
  const { t } = useTranslation('chat');
  const allowOnceRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onDecision('deny');
      }}
    >
      <DialogContent
        hideClose
        role="alertdialog"
        aria-modal="true"
        aria-label={`${t('approval.title')}: ${approval.toolName}`}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          allowOnceRef.current?.focus();
        }}
        className="max-w-lg"
      >
        <DialogHeader className="bg-warning-bg">
          <div className="flex items-start gap-3">
            <span className="rounded-lg bg-surface p-2 text-warning-fg shadow-e1">
              <ShieldAlert className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <DialogTitle>{t('approval.title')}</DialogTitle>
              <DialogDescription>
                <span className="font-medium text-fg-primary bidi-isolate">
                  {approval.toolName}
                </span>{' '}
                {t('approval.description')}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <DialogBody>
          <div className="mb-2 flex items-center justify-between text-micro text-fg-muted">
            <span>{t('approval.arguments')}</span>
            <span>{t('approval.risk', { value: approval.risk })}</span>
          </div>
          <pre className="ltr-island selectable max-h-40 overflow-auto rounded-lg bg-sunken p-3 text-code text-fg-secondary">
            {approval.argsSummary}
          </pre>
        </DialogBody>
        <DialogFooter className="flex-wrap">
          <Button variant="ghost" onClick={() => onDecision('deny')}>
            {t('approval.deny')}
          </Button>
          <Button variant="secondary" onClick={() => onDecision('allow_always_session')}>
            {t('approval.alwaysAllow')}
          </Button>
          <Button ref={allowOnceRef} variant="primary" onClick={() => onDecision('allow_once')}>
            {t('approval.allowOnce')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
