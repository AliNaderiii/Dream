/** Global keyboard shortcuts and complete command-palette registry. */

import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { LANGUAGES, useTranslation } from '@/lib/i18n';
import { windowApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { Accent, Density, ThemeMode } from '@/types';

export interface CommandItem {
  id: string;
  keys?: readonly string[];
  description: string;
  category: string;
  keywords?: string[];
  run: () => void;
  /** Fire even while a text field has focus. */
  allowInInput?: boolean;
}

/** Backward-compatible name for call sites that register a keyboard command. */
export type Shortcut = CommandItem;

/** True when the event target is a text-entry surface. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
}

/** Tests an event against a key combination. */
function matches(event: KeyboardEvent, keys: readonly string[]): boolean {
  const wantMod = keys.includes('mod');
  const wantShift = keys.includes('shift');
  const wantAlt = keys.includes('alt');
  const key = keys.find((item) => !['mod', 'shift', 'alt'].includes(item));
  if (!key) return false;

  const modPressed = event.metaKey || event.ctrlKey;
  return (
    event.key.toLowerCase() === key.toLowerCase() &&
    modPressed === wantMod &&
    event.shiftKey === wantShift &&
    event.altKey === wantAlt
  );
}

interface RouteCommand {
  id: string;
  path: string;
  key: string;
  keys?: readonly string[];
  tool?: boolean;
}

const ROUTES: readonly RouteCommand[] = [
  { id: 'dashboard', path: '/', key: 'nav.dashboard', keys: ['mod', '1'] },
  { id: 'chat', path: '/chat', key: 'nav.chat' },
  { id: 'projects', path: '/projects', key: 'nav.projects', keys: ['mod', '2'] },
  { id: 'memory', path: '/memory', key: 'nav.memory', keys: ['mod', '3'] },
  { id: 'providers', path: '/providers', key: 'nav.providers' },
  { id: 'settings', path: '/settings', key: 'nav.settings', keys: ['mod', ','] },
  { id: 'skills', path: '/skills', key: 'nav.skills', keys: ['mod', '4'], tool: true },
  { id: 'scheduler', path: '/scheduler', key: 'nav.scheduler', tool: true },
  { id: 'subagents', path: '/subagents', key: 'nav.subagents', tool: true },
  { id: 'data', path: '/data', key: 'nav.data', tool: true },
  { id: 'connectivity', path: '/connectivity', key: 'nav.connectivity', tool: true },
  { id: 'provenance', path: '/provenance', key: 'nav.provenance', tool: true },
] as const;

const THEMES: ThemeMode[] = ['light', 'warm', 'dark', 'system'];
const ACCENTS: Accent[] = ['forest', 'ocean', 'ember', 'violet'];
const DENSITIES: Density[] = ['comfortable', 'dense'];
const ZOOM_STOPS = [80, 100, 125, 150];

/**
 * Registers Dream's global shortcuts and returns every palette command:
 * navigation, sessions, settings, tools, locale, theme, density, and zoom.
 */
export function useKeyboardShortcuts(): CommandItem[] {
  const { t } = useTranslation('common');
  const { t: ts } = useTranslation('settings');
  const { t: tSearch } = useTranslation('search');
  const navigate = useNavigate();
  const sessions = useSessionStore((state) => state.sessions);
  const createSession = useSessionStore((state) => state.createSession);
  const setActiveSession = useSessionStore((state) => state.setActiveSession);
  const toggleCommandPalette = useAppStore((state) => state.toggleCommandPalette);
  const toggleSessionSearch = useAppStore((state) => state.toggleSessionSearch);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const toggleTheme = useAppStore((state) => state.toggleTheme);
  const setTheme = useAppStore((state) => state.setTheme);
  const setAccent = useAppStore((state) => state.setAccent);
  const setDensity = useAppStore((state) => state.setDensity);
  const setZoom = useAppStore((state) => state.setZoom);
  const setLocale = useAppStore((state) => state.setLocale);
  const setReduceMotion = useAppStore((state) => state.setReduceMotion);
  const reduceMotion = useAppStore((state) => state.reduceMotion);

  const commands = useMemo<CommandItem[]>(() => {
    const categories = {
      actions: t('command.categories.actions'),
      navigation: t('command.categories.navigation'),
      sessions: t('command.categories.sessions'),
      tools: t('command.categories.tools'),
      appearance: t('command.categories.appearance'),
      language: t('command.categories.language'),
    };

    const create = () => {
      const session = createSession(t('sessions.untitled'));
      void navigate(`/chat/${session.id}`);
    };

    const keyboard: CommandItem[] = [
      {
        id: 'palette.open',
        keys: ['mod', 'k'],
        description: t('command.open'),
        category: categories.actions,
        run: toggleCommandPalette,
        allowInInput: true,
      },
      {
        id: 'search.sessions',
        keys: ['mod', 'p'],
        description: tSearch('openCommand'),
        category: categories.actions,
        run: toggleSessionSearch,
        allowInInput: true,
      },
      {
        id: 'session.new',
        keys: ['mod', 'n'],
        description: t('command.newSession'),
        category: categories.actions,
        run: create,
      },
      {
        id: 'sidebar.toggle',
        keys: ['mod', 'b'],
        description: t('command.toggleSidebar'),
        category: categories.actions,
        run: toggleSidebar,
      },
      {
        id: 'theme.toggle',
        keys: ['mod', 'shift', 'l'],
        description: t('command.toggleTheme'),
        category: categories.appearance,
        run: toggleTheme,
      },
      {
        id: 'window.new',
        keys: ['mod', 'shift', 'n'],
        description: t('command.newWindow'),
        category: categories.actions,
        run: () => void windowApi.open({ route: '/' }),
      },
    ];

    const routeCommands: CommandItem[] = ROUTES.map((route) => ({
      id: `route.${route.id}`,
      ...(route.keys ? { keys: route.keys } : {}),
      description: t('command.openDestination', { destination: t(route.key) }),
      category: route.tool ? categories.tools : categories.navigation,
      keywords: [t(route.key)],
      run: () => void navigate(route.path),
    }));

    const sessionCommands: CommandItem[] = sessions.map((session) => ({
      id: `session.${session.id}`,
      description: session.title,
      category: categories.sessions,
      keywords: [t('sessions.title')],
      run: () => {
        setActiveSession(session.id);
        void navigate(`/chat/${session.id}`);
      },
    }));

    const themeCommands: CommandItem[] = THEMES.map((theme) => ({
      id: `theme.${theme}`,
      description: t('command.setTheme', { value: ts(`themeOptions.${theme}`) }),
      category: categories.appearance,
      run: () => setTheme(theme),
    }));
    const accentCommands: CommandItem[] = ACCENTS.map((accent) => ({
      id: `accent.${accent}`,
      description: t('command.setAccent', { value: ts(`accentOptions.${accent}`) }),
      category: categories.appearance,
      run: () => setAccent(accent),
    }));
    const densityCommands: CommandItem[] = DENSITIES.map((density) => ({
      id: `density.${density}`,
      description: t('command.setDensity', { value: ts(`densityOptions.${density}`) }),
      category: categories.appearance,
      run: () => setDensity(density),
    }));
    const zoomCommands: CommandItem[] = ZOOM_STOPS.map((zoom) => ({
      id: `zoom.${zoom}`,
      description: t('command.setZoom', { value: zoom }),
      category: categories.appearance,
      keywords: [ts('zoom')],
      run: () => setZoom(zoom),
    }));
    const localeCommands: CommandItem[] = LANGUAGES.map((language) => ({
      id: `locale.${language.code}`,
      description: t('command.switchLanguage', { value: t(language.nameKey) }),
      category: categories.language,
      run: () => setLocale(language.code),
    }));

    return [
      ...keyboard,
      ...routeCommands,
      ...sessionCommands,
      ...themeCommands,
      ...accentCommands,
      ...densityCommands,
      ...zoomCommands,
      {
        id: 'motion.reduce',
        description: reduceMotion ? ts('motionOptions.enable') : ts('motionOptions.reduce'),
        category: categories.appearance,
        run: () => setReduceMotion(!reduceMotion),
      },
      ...localeCommands,
    ];
  }, [
    createSession,
    navigate,
    reduceMotion,
    sessions,
    setAccent,
    setActiveSession,
    setDensity,
    setLocale,
    setReduceMotion,
    setTheme,
    setZoom,
    t,
    toggleCommandPalette,
    toggleSessionSearch,
    toggleSidebar,
    toggleTheme,
    tSearch,
    ts,
  ]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const typing = isTypingTarget(event.target);
      for (const command of commands) {
        if (!command.keys || (typing && !command.allowInInput)) continue;
        if (matches(event, command.keys)) {
          event.preventDefault();
          command.run();
          return;
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [commands]);

  return commands;
}
