/**
 * Global UI state: theme, direction, locale, layout chrome and agent status.
 *
 * Persisted to `localStorage` so appearance survives restarts independently of
 * the Rust-side window geometry, which `tauri-plugin-window-state` owns.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type {
  Accent,
  AgentStatus,
  Density,
  Direction,
  Locale,
  NumeralStyle,
  ResolvedTheme,
  ThemeMode,
} from '@/types';

interface AppState {
  /* appearance */
  theme: ThemeMode;
  /** Theme actually applied, after resolving `system`. */
  resolvedTheme: ResolvedTheme;
  direction: Direction;
  locale: Locale;
  density: Density;
  accent: Accent;
  /** Root UI scale as an integer percentage, clamped to 80–150. */
  zoom: number;
  reduceMotion: boolean;
  numerals: NumeralStyle;

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
  setAccent: (accent: Accent) => void;
  setZoom: (zoom: number) => void;
  setReduceMotion: (reduceMotion: boolean) => void;
  setNumerals: (numerals: NumeralStyle) => void;
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
export const MIN_UI_ZOOM = 80;
export const MAX_UI_ZOOM = 150;

type PersistedAppState = Pick<
  AppState,
  | 'theme'
  | 'locale'
  | 'direction'
  | 'density'
  | 'accent'
  | 'zoom'
  | 'reduceMotion'
  | 'numerals'
  | 'sidebarCollapsed'
  | 'sidebarWidth'
  | 'workspaceRoot'
>;

/** Keeps persisted settings from older releases trustworthy and in range. */
export function migrateAppState(persisted: unknown): PersistedAppState {
  const value =
    persisted && typeof persisted === 'object' ? (persisted as Record<string, unknown>) : {};
  const rawZoom = typeof value['zoom'] === 'number' ? value['zoom'] : 100;
  const density = value['density'] === 'compact' ? 'dense' : value['density'];
  return {
    theme: (value['theme'] as ThemeMode | undefined) ?? 'system',
    locale: (value['locale'] as Locale | undefined) ?? 'en',
    direction: (value['direction'] as Direction | undefined) ?? 'ltr',
    density: density === 'dense' ? 'dense' : 'comfortable',
    accent: (value['accent'] as Accent | undefined) ?? 'violet',
    zoom: Math.min(MAX_UI_ZOOM, Math.max(MIN_UI_ZOOM, Math.round(rawZoom))),
    reduceMotion: value['reduceMotion'] === true,
    numerals: value['numerals'] === 'persian' ? 'persian' : 'latin',
    sidebarCollapsed: value['sidebarCollapsed'] === true,
    sidebarWidth:
      typeof value['sidebarWidth'] === 'number' ? value['sidebarWidth'] : SIDEBAR_DEFAULT_WIDTH,
    workspaceRoot: typeof value['workspaceRoot'] === 'string' ? value['workspaceRoot'] : null,
  };
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'system',
      resolvedTheme: 'light',
      direction: 'ltr',
      locale: 'en',
      density: 'comfortable',
      accent: 'violet',
      zoom: 100,
      reduceMotion: false,
      numerals: 'latin',

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
      setAccent: (accent) => set({ accent }),
      setZoom: (zoom) =>
        set({ zoom: Math.min(MAX_UI_ZOOM, Math.max(MIN_UI_ZOOM, Math.round(zoom))) }),
      setReduceMotion: (reduceMotion) => set({ reduceMotion }),
      setNumerals: (numerals) => set({ numerals }),

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
      version: 2,
      migrate: (persisted) => migrateAppState(persisted),
      // Session-scoped and Rust-owned fields are deliberately not persisted.
      partialize: (state) => ({
        theme: state.theme,
        locale: state.locale,
        direction: state.direction,
        density: state.density,
        accent: state.accent,
        zoom: state.zoom,
        reduceMotion: state.reduceMotion,
        numerals: state.numerals,
        sidebarCollapsed: state.sidebarCollapsed,
        sidebarWidth: state.sidebarWidth,
        workspaceRoot: state.workspaceRoot,
      }),
    },
  ),
);
