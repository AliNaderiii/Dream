import { AlertCircle } from 'lucide-react';
import { forwardRef, useId } from 'react';
import type { ComponentProps, ReactNode } from 'react';

import { cn } from '@/utils/cn';

export interface InputProps extends ComponentProps<'input'> {
  label?: string;
  hint?: string;
  error?: string;
  leading?: ReactNode;
}

/** Labelled, described input with logical icon padding and non-color-only errors. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, id, label, hint, error, leading, 'aria-describedby': describedBy, ...props },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const messageId = `${inputId}-message`;
  const description = error ?? hint;

  return (
    <div className="flex min-w-0 flex-col gap-1 text-caption font-medium">
      {label && <label htmlFor={inputId}>{label}</label>}
      <span className="relative flex items-center">
        {leading && (
          <span
            className="pointer-events-none absolute start-3 text-fg-muted [&_svg]:size-4"
            aria-hidden
          >
            {leading}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={description ? messageId : describedBy}
          className={cn(
            'focus-control selectable control-md w-full rounded-md border border-border-default bg-surface text-body text-fg-primary placeholder:text-fg-muted',
            leading && 'ps-9',
            error && 'border-danger-fg pe-9',
            className,
          )}
          {...props}
        />
        {error && (
          <AlertCircle
            className="pointer-events-none absolute end-3 size-4 text-danger-fg"
            aria-hidden
          />
        )}
      </span>
      {description && (
        <span
          id={messageId}
          className={cn('text-micro', error ? 'text-danger-fg' : 'text-fg-muted')}
        >
          {description}
        </span>
      )}
    </div>
  );
});

export interface TextareaProps extends ComponentProps<'textarea'> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, id, label, hint, error, ...props },
  ref,
) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  const messageId = `${textareaId}-message`;
  const description = error ?? hint;
  return (
    <div className="flex min-w-0 flex-col gap-1 text-caption font-medium">
      {label && <label htmlFor={textareaId}>{label}</label>}
      <textarea
        ref={ref}
        id={textareaId}
        aria-invalid={error ? true : undefined}
        aria-describedby={description ? messageId : undefined}
        className={cn(
          'focus-control selectable min-h-20 resize-y rounded-md border border-border-default bg-surface px-3 py-2 text-body text-fg-primary placeholder:text-fg-muted',
          error && 'border-danger-fg',
          className,
        )}
        {...props}
      />
      {description && (
        <span
          id={messageId}
          className={cn('text-micro', error ? 'text-danger-fg' : 'text-fg-muted')}
        >
          {description}
        </span>
      )}
    </div>
  );
});
