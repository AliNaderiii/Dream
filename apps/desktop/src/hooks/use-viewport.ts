/**
 * Viewport breakpoint detection for the shared shell (desktop + web gateway).
 *
 * Breakpoints are deterministic test targets, not device claims:
 *   phonePortrait     <= 428 px
 *   phoneLandscape   429-600 px
 *   tabletPortrait   601-828 px
 *   tabletLandscape  829-1024 px
 *   desktop          >= 1025 px
 *
 * In unit tests, override window.innerWidth and/or window.matchMedia
 * via the test setup (see responsive.test.tsx).
 */

import { useEffect, useState } from 'react';

export type Breakpoint =
  | 'phonePortrait'
  | 'phoneLandscape'
  | 'tabletPortrait'
  | 'tabletLandscape'
  | 'desktop';

const BOUNDS = {
  phonePortrait: 428,
  phoneLandscape: 600,
  tabletPortrait: 828,
  tabletLandscape: 1024,
};

function classify(width: number): Breakpoint {
  if (width <= BOUNDS.phonePortrait) return 'phonePortrait';
  if (width <= BOUNDS.phoneLandscape) return 'phoneLandscape';
  if (width <= BOUNDS.tabletPortrait) return 'tabletPortrait';
  if (width <= BOUNDS.tabletLandscape) return 'tabletLandscape';
  return 'desktop';
}

export function isBottomNavBreakpoint(bp: Breakpoint): boolean {
  return bp === 'phonePortrait' || bp === 'phoneLandscape';
}

export function isDrawerBreakpoint(bp: Breakpoint): boolean {
  return bp !== 'desktop';
}

export interface ViewportState {
  breakpoint: Breakpoint;
  width: number;
  setSidebarDrawerOpen: (open: boolean) => void;
  sidebarDrawerOpen: boolean;
}

function useIsTauri(): boolean {
  if (typeof window === 'undefined') return false;
  return '__TAURI_INTERNALS__' in window;
}

export function useViewport(): ViewportState {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => {
    // In jsdom (vitest) window.innerWidth is 0 by default; treat that as
    // desktop so the existing desktop shell tests keep working without a
    // separate test-setup override.
    if (typeof window === 'undefined' || window.innerWidth <= 0) {
      return 'desktop';
    }
    return classify(window.innerWidth);
  });
  const [width, setWidth] = useState<number>(() => {
    if (typeof window === 'undefined' || window.innerWidth <= 0) {
      return 1280;
    }
    return window.innerWidth;
  });
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onResize = () => {
      setWidth(window.innerWidth);
      setBreakpoint(classify(window.innerWidth));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Provide a toggle that collapses at desktop breakpoints too, so the
  // desktop Sidebar can still drive drawer open/close state across the
  // breakpoint boundary without jank.
  const setSidebarDrawerOpen = (open: boolean) => setDrawerOpen(open);

  let sidebarDrawerOpen = drawerOpen;
  if (!isDrawerBreakpoint(breakpoint)) {
    sidebarDrawerOpen = false;
  }

  return {
    breakpoint,
    width,
    setSidebarDrawerOpen,
    sidebarDrawerOpen,
  };
}
