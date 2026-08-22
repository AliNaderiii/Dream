import { beforeEach, describe, expect, it } from 'vitest';

import {
  MAX_UI_ZOOM,
  migrateAppState,
  MIN_UI_ZOOM,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  useAppStore,
} from '@/stores/use-app-store';

const initial = useAppStore.getState();

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState(initial, true);
  });

  it('toggles the sidebar', () => {
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
  });

  it('clamps the sidebar width to the allowed range', () => {
    useAppStore.getState().setSidebarWidth(50);
    expect(useAppStore.getState().sidebarWidth).toBe(SIDEBAR_MIN_WIDTH);

    useAppStore.getState().setSidebarWidth(9999);
    expect(useAppStore.getState().sidebarWidth).toBe(SIDEBAR_MAX_WIDTH);
  });

  it('switches direction to RTL when the locale becomes Persian', () => {
    useAppStore.getState().setLocale('fa');
    expect(useAppStore.getState().direction).toBe('rtl');

    useAppStore.getState().setLocale('en');
    expect(useAppStore.getState().direction).toBe('ltr');
  });

  it('toggles the theme away from the resolved value', () => {
    useAppStore.setState({ theme: 'system', resolvedTheme: 'light' });
    useAppStore.getState().toggleTheme();
    expect(useAppStore.getState().theme).toBe('dark');

    useAppStore.setState({ resolvedTheme: 'dark' });
    useAppStore.getState().toggleTheme();
    expect(useAppStore.getState().theme).toBe('light');
  });

  it('clamps zoom and persists the complete appearance model', () => {
    useAppStore.getState().setZoom(12);
    expect(useAppStore.getState().zoom).toBe(MIN_UI_ZOOM);
    useAppStore.getState().setZoom(999);
    expect(useAppStore.getState().zoom).toBe(MAX_UI_ZOOM);

    useAppStore.getState().setTheme('warm');
    useAppStore.getState().setAccent('ocean');
    useAppStore.getState().setDensity('dense');
    useAppStore.getState().setReduceMotion(true);
    expect(useAppStore.getState()).toMatchObject({
      theme: 'warm',
      accent: 'ocean',
      density: 'dense',
      reduceMotion: true,
    });
  });

  it('migrates legacy compact density without trusting invalid zoom', () => {
    expect(migrateAppState({ density: 'compact', zoom: 200 })).toMatchObject({
      density: 'dense',
      zoom: MAX_UI_ZOOM,
    });
  });

  it('tracks agent status and pending approvals', () => {
    useAppStore.getState().setAgentStatus('running');
    useAppStore.getState().setPendingApprovals(3);

    expect(useAppStore.getState().agentStatus).toBe('running');
    expect(useAppStore.getState().pendingApprovals).toBe(3);
  });
});
