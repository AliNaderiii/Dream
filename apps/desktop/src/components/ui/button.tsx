import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import type { ComponentProps } from 'react';

import { cn } from '@/utils/cn';

/**
 * Button variants per design-system §8: primary, secondary, ghost, destructive,
 * danger-outline; sizes sm 28 / md 32 / lg 40.
 */
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-body font-medium transition-colors duration-fast ease-standard disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        primary: 'bg-accent text-fg-inverse hover:opacity-90 active:opacity-80',
        secondary:
          'bg-surface text-fg-primary border border-border-default hover:bg-surface-2 active:bg-sunken',
        ghost: 'text-fg-secondary hover:bg-surface-2 hover:text-fg-primary',
        destructive: 'bg-danger-fg text-white hover:opacity-90',
        'danger-outline': 'border border-danger-fg text-danger-fg hover:bg-danger-bg',
      },
      size: {
        sm: 'h-7 px-2.5 text-caption [&_svg]:size-4',
        md: 'h-8 px-3 [&_svg]:size-4',
        lg: 'h-10 px-4 text-body-lg [&_svg]:size-5',
        icon: 'size-8 [&_svg]:size-4',
        'icon-sm': 'size-7 [&_svg]:size-4',
      },
    },
    defaultVariants: { variant: 'secondary', size: 'md' },
  },
);

export interface ButtonProps extends ComponentProps<'button'>, VariantProps<typeof buttonVariants> {
  /** Render as the child element instead of a `<button>` (Radix `Slot`). */
  asChild?: boolean;
}

/** Primary interactive control. */
export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button';
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
