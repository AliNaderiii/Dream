/**
 * Modal dialog built on `@radix-ui/react-dialog`.
 *
 * Radix owns focus trapping, focus restore on close, `Escape` handling and the
 * `aria-modal` wiring, so every dialog in the app inherits the accessibility
 * contract from design-system §8. Motion is expressed with the shared duration
 * tokens; `prefers-reduced-motion` collapses them globally in `theme.css`.
 */

import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ComponentProps } from 'react';

import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

/** Dimmed backdrop behind a modal surface. */
export function DialogOverlay({
  className,
  ...props
}: ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      className={cn('motion-enter fixed inset-0 z-50 bg-black/50', className)}
      {...props}
    />
  );
}

export interface DialogContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  /** Hide the built-in close affordance (for dialogs with explicit actions only). */
  hideClose?: boolean;
}

/** Centred modal surface. */
export function DialogContent({ className, children, hideClose, ...props }: DialogContentProps) {
  const { t } = useTranslation('common');
  return (
    <DialogPrimitive.Portal>
      <DialogOverlay />
      <DialogPrimitive.Content
        className={cn(
          'motion-enter fixed start-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(var(--overlay-md),92vw)] -translate-x-1/2 -translate-y-1/2 flex-col',
          'overflow-hidden rounded-xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2',
          className,
        )}
        {...props}
      >
        {children}
        {!hideClose && (
          <DialogPrimitive.Close
            className="absolute end-3 top-3 rounded-sm p-1 text-fg-muted transition-colors duration-fast hover:bg-surface-2 hover:text-fg-primary"
            aria-label={t('generic.close')}
          >
            <X className="size-4" aria-hidden />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** Header block: title plus optional description. */
export function DialogHeader({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn('flex flex-col gap-1 border-b border-border-default px-5 py-4', className)}
      {...props}
    />
  );
}

/** Footer with trailing-aligned actions. */
export function DialogFooter({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'flex items-center justify-end gap-2 border-t border-border-default px-5 py-3',
        className,
      )}
      {...props}
    />
  );
}

/** Accessible dialog title — required by Radix for `aria-labelledby`. */
export function DialogTitle({ className, ...props }: ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className={cn('pe-6 text-h3 font-semibold text-fg-primary', className)}
      {...props}
    />
  );
}

/** Supporting copy under the title. */
export function DialogDescription({
  className,
  ...props
}: ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className={cn('text-caption text-fg-secondary', className)}
      {...props}
    />
  );
}

/** Scrollable body between header and footer. */
export function DialogBody({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('min-h-0 flex-1 overflow-y-auto px-5 py-4', className)} {...props} />;
}
