/**
 * Reusable destructive-action confirmation.
 *
 * Radix focuses the first tabbable control on open and restores focus to the
 * trigger on close, so keyboard users never lose their place (design-system
 * §8, "destructive actions always confirm").
 */

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Renders the confirm button in the destructive style. */
  destructive?: boolean;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = true,
  onConfirm,
}: ConfirmDialogProps) {
  const { t } = useTranslation('common');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(28rem,92vw)]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogBody className="sr-only" aria-hidden />
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            {cancelLabel ?? t('confirm.cancel')}
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'primary'}
            onClick={() => {
              onConfirm();
              onOpenChange(false);
            }}
          >
            {confirmLabel ?? t('confirm.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
