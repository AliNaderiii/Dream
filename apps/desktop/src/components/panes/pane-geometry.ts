import type { DockEdge } from '@/stores/use-layout-store';

/** Map a physical drop point to the store's logical before/after edge names. */
export function dockEdgeAt(x: number, y: number, rtl: boolean): DockEdge {
  if (x < 0.25) return rtl ? 'right' : 'left';
  if (x > 0.75) return rtl ? 'left' : 'right';
  if (y < 0.5) return 'top';
  return 'bottom';
}
