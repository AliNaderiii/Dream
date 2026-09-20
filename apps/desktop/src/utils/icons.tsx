/**
 * Safe icon rendering utilities.
 *
 * Provides a component for safely rendering lucide-react icons, especially
 * important when icons are imported alongside react-router's Route in the
 * same bundle. Minification can sometimes cause issues where a function
 * component becomes undefined.
 */

import type { LucideIcon } from 'lucide-react';
import { forwardRef, type ComponentProps } from 'react';

/**
 * Props for the safe icon component.
 */
interface SafeIconProps extends Omit<ComponentProps<'svg'>, 'ref'> {
  /** The icon component to render. */
  icon: LucideIcon | undefined | null;
  /** Additional className to apply. */
  className?: string;
}

/**
 * Safely renders a lucide-react icon, returning null if the icon is not
 * a valid function component. This prevents "G is not a function" errors
 * that can occur in production bundles when icons become undefined.
 *
 * Usage:
 * ```tsx
 * import { SafeIcon } from '@/utils/icons';
 * import { SomeIcon } from 'lucide-react';
 *
 * // Safe usage - returns null if SomeIcon is invalid
 * <SafeIcon icon={SomeIcon} className="size-4" aria-hidden />
 * ```
 */
export const SafeIcon = forwardRef<SVGSVGElement, SafeIconProps>(
  ({ icon, className, ...props }, ref) => {
    if (typeof icon !== 'function') {
      return null;
    }
    const Icon = icon;
    return <Icon ref={ref} className={className} {...props} />;
  },
);

SafeIcon.displayName = 'SafeIcon';
