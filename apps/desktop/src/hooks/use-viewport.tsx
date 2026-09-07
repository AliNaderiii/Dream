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
 *
 * Drawer state is shared via ViewportProvider context so that AppShell and
 * SidebarDrawer observe the same open/close state.
 */

import { createContext, useEffect, useContext, useRef, useState } from 'react';

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

interface ViewportContextValue extends ViewportState {
  viewportRef: React.RefObject<HTMLDivElement | null>;
}

const ViewportContext = createContext<ViewportContextValue | null>(null);

export function useViewport(): ViewportState {
  const ctx = useContext(ViewportContext);
  if (ctx !== null) {
    return ctx;
  }
  throw new Error(
    'useViewport must be used within a ViewportProvider. Wrap the app shell with ViewportProvider.',
  );
}

/** Fallback hook for isolated component tests (e.g. SidebarDrawer standalone). */
export function useViewportFallback(): ViewportState {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => {
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
    // Sync with current window.innerWidth on mount — the lazy initializer
    // may have read a stale value in jsdom-based test environments where
    // innerWidth is set before the first render.
    setWidth(window.innerWidth);
    setBreakpoint(classify(window.innerWidth));
    const onResize = () => {
      setWidth(window.innerWidth);
      setBreakpoint(classify(window.innerWidth));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  let sidebarDrawerOpen = drawerOpen;
  if (!isDrawerBreakpoint(breakpoint)) {
    sidebarDrawerOpen = false;
  }

  return {
    breakpoint,
    width,
    setSidebarDrawerOpen: setDrawerOpen,
    sidebarDrawerOpen,
  };
}

export function ViewportProvider({ children }: { children: React.ReactNode }) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => {
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
  // Default the drawer to open at drawer breakpoints (matching the approved UX
  // decision); closed on desktop.
  const initialBreakpoint = typeof window === 'undefined' || window.innerWidth <= 0
    ? 'desktop'
    : classify(window.innerWidth);
  const [drawerOpen, setDrawerOpen] = useState(isDrawerBreakpoint(initialBreakpoint));

  useEffect(() => {
    if (typeof window === 'undefined') return;
    // Sync with current window.innerWidth on mount — the lazy initializer
    // may have read a stale value in jsdom-based test environments where
    // innerWidth is set before the first render.
    setWidth(window.innerWidth);
    setBreakpoint(classify(window.innerWidth));
    const onResize = () => {
      setWidth(window.innerWidth);
      setBreakpoint(classify(window.innerWidth));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const setSidebarDrawerOpen = (open: boolean) => setDrawerOpen(open);

  let sidebarDrawerOpen = drawerOpen;
  if (!isDrawerBreakpoint(breakpoint)) {
    sidebarDrawerOpen = false;
  }

  const value: ViewportContextValue = {
    breakpoint,
    width,
    setSidebarDrawerOpen,
    sidebarDrawerOpen,
    viewportRef,
  };

  return (
    <ViewportContext.Provider value={value}>
      {children}
    </ViewportContext.Provider>
  );
}
