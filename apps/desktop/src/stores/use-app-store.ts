/**
 * Global UI state: theme, direction, locale, layout chrome and agent status.
 *
 * Persisted to `localStorage` so appearance survives restarts independently of
 * the Rust-side window geometry, which `tauri-plugin-window-state` owns.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { AgentStatus, Density, Direction, Locale, ResolvedTheme, ThemeMode } from '@/types';

interface AppState {
  /* appearance */
  theme: ThemeMode;
  /** Theme actually applied, after resolving `system`. */
  resolvedTheme: ResolvedTheme;
  direction: Direction;
  locale: Locale;
  density: Density;

  /* layout */
  sidebarCollapsed: boolean;
  sidebarWidth: number;
  commandPaletteOpen: boolean;

  /* agent (mirrored from Rust) */
  agentStatus: AgentStatus;
  pendingApprovals: number;
  workspaceRoot: string | null;

  /* actions */
  setTheme: (theme: ThemeMode) => void;
  setResolvedTheme: (theme: ResolvedTheme) => void;
  toggleTheme: () => void;
  setLocale: (locale: Locale) => void;
  setDirection: (direction: Direction) => void;
  setDensity: (density: Density) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setSidebarWidth: (width: number) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
  setAgentStatus: (status: AgentStatus) => void;
  setPendingApprovals: (count: number) => void;
  setWorkspaceRoot: (path: string | null) => void;
}

/** Minimum and maximum sidebar widths, per the design system's layout rules. */
export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 420;
export const SIDEBAR_DEFAULT_WIDTH = 260;

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'system',
      resolvedTheme: 'light',
      direction: 'ltr',
      locale: 'en',
      density: 'comfortable',

      sidebarCollapsed: false,
      sidebarWidth: SIDEBAR_DEFAULT_WIDTH,
      commandPaletteOpen: false,

      agentStatus: 'idle',
      pendingApprovals: 0,
      workspaceRoot: null,

      setTheme: (theme) => set({ theme }),
      setResolvedTheme: (resolvedTheme) => set({ resolvedTheme }),
      // Cycles the explicit choice only: system → light → dark → light …
      toggleTheme: () =>
        set((state) => ({
          theme: state.resolvedTheme === 'dark' ? 'light' : 'dark',
        })),
      // Locale and direction move together; Persian is RTL.
      setLocale: (locale) => set({ locale, direction: locale === 'fa' ? 'rtl' : 'ltr' }),
      setDirection: (direction) => set({ direction }),
      setDensity: (density) => set({ density }),

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setSidebarWidth: (width) =>
        set({ sidebarWidth: Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width)) }),
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
      toggleCommandPalette: () =>
        set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),

      setAgentStatus: (agentStatus) => set({ agentStatus }),
      setPendingApprovals: (pendingApprovals) => set({ pendingApprovals }),
      setWorkspaceRoot: (workspaceRoot) => set({ workspaceRoot }),
    }),
    {
      name: 'dream.app',
      // Session-scoped and Rust-owned fields are deliberately not persisted.
      partialize: (state) => ({
        theme: state.theme,
        locale: state.locale,
        direction: state.direction,
        density: state.density,
        sidebarCollapsed: state.sidebarCollapsed,
        sidebarWidth: state.sidebarWidth,
        workspaceRoot: state.workspaceRoot,
      }),
    },
  ),
);
