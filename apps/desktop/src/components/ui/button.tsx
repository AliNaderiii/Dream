import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { LoaderCircle } from 'lucide-react';
import type { ComponentProps } from 'react';

import { cn } from '@/utils/cn';

/** Five semantic button variants and density-aware sm/md/lg controls. */
const buttonVariants = cva(
  'relative inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium',
  {
    variants: {
      variant: {
        primary:
          'bg-accent text-accent-fg shadow-e1 transition-[background-color,transform,opacity] duration-fast ease-standard hover:bg-accent-hover active:scale-[0.98]',
        secondary:
          'border border-border-default bg-surface text-fg-primary transition-[background-color,border-color,transform] duration-fast ease-standard hover:border-border-strong hover:bg-surface-2 active:scale-[0.98]',
        ghost:
          'text-fg-secondary transition-[background-color,color,transform] duration-fast ease-standard hover:bg-surface-2 hover:text-fg-primary active:scale-[0.98]',
        destructive:
          'bg-danger-fg text-surface shadow-e1 transition-[filter,transform] duration-fast ease-standard hover:brightness-90 active:scale-[0.98]',
        'danger-outline':
          'border border-danger-fg text-danger-fg transition-[background-color,transform] duration-fast ease-standard hover:bg-danger-bg active:scale-[0.98]',
      },
      size: {
        sm: 'control-sm text-caption [&_svg]:size-4',
        md: 'control-md text-body [&_svg]:size-4',
        lg: 'control-lg text-body-lg [&_svg]:size-5',
        icon: 'size-(--control-height-md) [&_svg]:size-4',
        'icon-sm': 'size-(--control-height-sm) [&_svg]:size-4',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
);

export interface ButtonProps extends ComponentProps<'button'>, VariantProps<typeof buttonVariants> {
  /** Render as the child element instead of a `<button>` (Radix `Slot`). */
  asChild?: boolean;
  /** Replaces visible content with an in-place spinner; measured width is retained. */
  loading?: boolean;
}

/** Primary interactive control. */
export function Button({
  className,
  variant,
  size,
  asChild = false,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(
    buttonVariants({ variant, size }),
    'disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
    className,
  );

  // Slot requires one direct element. Loading visuals are therefore a native-button concern.
  if (asChild) {
    return (
      <Slot className={classes} aria-busy={loading || undefined} {...props}>
        {children}
      </Slot>
    );
  }

  return (
    <button
      className={classes}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      {...props}
    >
      <span className={cn('contents', loading && 'invisible')}>{children}</span>
      {loading && (
        <LoaderCircle
          className="absolute size-4 animate-spin"
          aria-hidden
          data-testid="button-spinner"
        />
      )}
    </button>
  );
}

export { buttonVariants };
