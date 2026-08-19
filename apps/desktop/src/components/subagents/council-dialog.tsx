/**
 * Council review dialog — the opt-in entry point for a three-role council.
 *
 * The council is started with `council.run` and one topic; every member
 * defaults to the offline echo provider (the sidecar's rule too), so the
 * first run works with no credentials and nothing leaves the machine unless
 * the caller overrides a role's provider.
 */

import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useId, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';

interface CouncilDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Receives the trimmed topic and calls `council.run`. */
  onRun: (topic: string) => Promise<void> | void;
}

const fieldClass =
  'selectable w-full rounded-md border border-border-default bg-surface px-2.5 py-1.5 text-body text-fg-primary placeholder:text-fg-muted focus:border-border-strong focus:outline-none';

export function CouncilDialog({ open, onOpenChange, onRun }: CouncilDialogProps) {
  const { t } = useTranslation('subagents');
  const [topic, setTopic] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  const submit = async () => {
    if (!topic.trim()) {
      setError(t('councilTopicRequired'));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onRun(topic.trim());
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content
          aria-labelledby={titleId}
          className="fixed start-1/2 top-12 z-50 flex max-h-[85vh] w-[min(36rem,92vw)] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2"
        >
          <header className="flex items-center justify-between border-b border-border-default px-4 py-3">
            <div>
              <Dialog.Title id={titleId} className="text-h3 font-semibold">
                {t('councilReview')}
              </Dialog.Title>
              <Dialog.Description className="text-caption text-fg-secondary">
                {t('councilReviewDesc')}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-sm" aria-label={t('councilClose')}>
                <X aria-hidden />
              </Button>
            </Dialog.Close>
          </header>

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
            <label className="flex flex-col gap-1">
              <span className="text-caption font-medium text-fg-secondary">
                {t('councilTopic')}
              </span>
              <textarea
                className={`${fieldClass} min-h-24 resize-y`}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder={t('councilTopicPlaceholder')}
                autoFocus
              />
            </label>
            <p className="text-micro text-fg-muted">{t('councilEchoHint')}</p>
            {error && (
              <p role="alert" className="text-caption text-danger-fg">
                {error}
              </p>
            )}
          </div>

          <footer className="flex items-center justify-between gap-3 border-t border-border-default px-4 py-3">
            <Dialog.Close asChild>
              <Button variant="ghost">{t('councilCancel')}</Button>
            </Dialog.Close>
            <Button variant="primary" disabled={busy} onClick={() => void submit()}>
              {busy ? t('councilStarting') : t('runCouncil')}
            </Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
