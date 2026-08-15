/**
 * Global keyboard shortcut system.
 *
 * `mod` maps to ⌘ on macOS and Ctrl elsewhere. Shortcuts are suppressed while the
 * user is typing in an input, textarea or contenteditable, except for ⌘K which
 * must always reach the command palette (accessibility contract, design-system §10).
 */

import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import { windowApi } from '@/lib/tauri';

/** A single registered shortcut. */
export interface Shortcut {
  /** Key combination, e.g. `['mod', 'k']`. */
  keys: readonly string[];
  /** Human-readable description, shown in the command palette and help. */
  description: string;
  /** Handler invoked when the combination fires. */
  run: () => void;
  /** Fire even while a text field has focus. */
  allowInInput?: boolean;
}

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
  const key = keys.find((k) => !['mod', 'shift', 'alt'].includes(k));
  if (!key) return false;

  const modPressed = event.metaKey || event.ctrlKey;
  return (
    event.key.toLowerCase() === key.toLowerCase() &&
    modPressed === wantMod &&
    event.shiftKey === wantShift &&
    event.altKey === wantAlt
  );
}

/**
 * Registers Dream's global shortcuts. Mount once, at the app root.
 *
 * Returns the shortcut list so the command palette can render it.
 */
export function useKeyboardShortcuts(): Shortcut[] {
  const navigate = useNavigate();
  const toggleCommandPalette = useAppStore((s) => s.toggleCommandPalette);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const createSession = useSessionStore((s) => s.createSession);

  const shortcuts = useMemo<Shortcut[]>(
    () => [
      {
        keys: ['mod', 'k'],
        description: 'Open command palette',
        run: toggleCommandPalette,
        allowInInput: true,
      },
      {
        keys: ['mod', 'n'],
        description: 'New session',
        run: () => {
          const session = createSession();
          void navigate(`/chat/${session.id}`);
        },
      },
      { keys: ['mod', 'b'], description: 'Toggle sidebar', run: toggleSidebar },
      { keys: ['mod', 'shift', 'l'], description: 'Toggle light / dark theme', run: toggleTheme },
      { keys: ['mod', '1'], description: 'Go to dashboard', run: () => void navigate('/') },
      { keys: ['mod', '2'], description: 'Go to projects', run: () => void navigate('/projects') },
      { keys: ['mod', '3'], description: 'Go to memory', run: () => void navigate('/memory') },
      { keys: ['mod', '4'], description: 'Go to skills', run: () => void navigate('/skills') },
      { keys: ['mod', ','], description: 'Open settings', run: () => void navigate('/settings') },
      {
        keys: ['mod', 'shift', 'n'],
        description: 'Open a new window',
        run: () => void windowApi.open({ route: '/' }),
      },
    ],
    [navigate, toggleCommandPalette, toggleSidebar, toggleTheme, createSession],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const typing = isTypingTarget(event.target);
      for (const shortcut of shortcuts) {
        if (typing && !shortcut.allowInInput) continue;
        if (matches(event, shortcut.keys)) {
          event.preventDefault();
          shortcut.run();
          return;
        }
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [shortcuts]);

  return shortcuts;
}
