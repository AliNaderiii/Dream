/**
 * ⌘K command palette.
 *
 * Every registered shortcut is reachable here, satisfying the accessibility
 * contract that the palette can drive every command (design-system §10).
 */

import * as Dialog from '@radix-ui/react-dialog';
import { useMemo, useState } from 'react';

import type { Shortcut } from '@/hooks/use-keyboard-shortcuts';
import { useTranslation } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

interface CommandPaletteProps {
  /** Commands to offer, normally the global shortcut list. */
  commands: Shortcut[];
}

export function CommandPalette({ commands }: CommandPaletteProps) {
  const { t } = useTranslation('common');
  const open = useAppStore((s) => s.commandPaletteOpen);
  const setOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.description.toLowerCase().includes(q));
  }, [commands, query]);

  // Clamp during render rather than in an effect: deriving the value avoids the
  // extra render pass a setState-in-effect would cost, and it can never be stale.
  const activeIndex = Math.min(highlighted, Math.max(results.length - 1, 0));

  const runCommand = (command: Shortcut) => {
    setOpen(false);
    command.run();
  };

  const handleOpenChange = (next: boolean) => {
    // Reset the query as the palette opens so each invocation starts clean.
    if (next) {
      setQuery('');
      setHighlighted(0);
    }
    setOpen(next);
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content
          aria-label={t('command.title')}
          className="fixed start-1/2 top-24 z-50 w-[min(36rem,90vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2"
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setHighlighted((activeIndex + 1) % Math.max(results.length, 1));
            }
            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setHighlighted((activeIndex - 1 + results.length) % Math.max(results.length, 1));
            }
            if (event.key === 'Enter') {
              event.preventDefault();
              const command = results[activeIndex];
              if (command) runCommand(command);
            }
          }}
        >
          <Dialog.Title className="sr-only">{t('command.title')}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('command.description')}</Dialog.Description>

          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('command.searchPlaceholder')}
            aria-label={t('command.searchAria')}
            className="selectable h-12 w-full border-b border-border-default bg-transparent px-4 text-body-lg text-fg-primary placeholder:text-fg-muted focus:outline-none"
          />

          <ul className="max-h-80 overflow-y-auto p-2">
            {results.length === 0 ? (
              <li className="px-3 py-6 text-center text-caption text-fg-muted">
                {t('command.empty')}
              </li>
            ) : (
              results.map((command, index) => (
                <li key={command.description}>
                  <button
                    type="button"
                    onMouseEnter={() => setHighlighted(index)}
                    onClick={() => runCommand(command)}
                    className={cn(
                      'flex w-full items-center justify-between rounded-md px-3 py-2 text-start text-body',
                      index === activeIndex ? 'bg-accent-soft text-accent-text' : 'text-fg-primary',
                    )}
                  >
                    <span>{command.description}</span>
                    <span className="ltr-island text-caption text-fg-muted">
                      {formatShortcut(command.keys)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
