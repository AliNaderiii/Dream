/** Fast, keyboard-complete ⌘K command palette with bilingual fuzzy search. */

import * as Dialog from '@radix-ui/react-dialog';
import { Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { searchCommands } from '@/components/shared/command-search';
import type { CommandItem } from '@/hooks/use-keyboard-shortcuts';
import { useTranslation } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

interface CommandPaletteProps {
  commands: CommandItem[];
}

export function CommandPalette({ commands }: CommandPaletteProps) {
  const { t } = useTranslation('common');
  const open = useAppStore((state) => state.commandPaletteOpen);
  const setOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);

  const results = useMemo(() => searchCommands(commands, query), [commands, query]);
  const activeIndex = Math.min(highlighted, Math.max(results.length - 1, 0));
  const listId = 'dream-command-results';
  const activeId = results[activeIndex] ? `dream-command-${activeIndex}` : undefined;

  const runCommand = (command: CommandItem) => {
    command.run();
    setOpen(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setQuery('');
      setHighlighted(0);
    }
    setOpen(next);
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="motion-enter fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content
          aria-label={t('command.title')}
          className="motion-enter fixed start-1/2 top-20 z-50 w-[min(var(--overlay-md),92vw)] -translate-x-1/2 overflow-hidden rounded-2xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2"
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setHighlighted((activeIndex + 1) % Math.max(results.length, 1));
            }
            if (event.key === 'ArrowUp') {
              event.preventDefault();
              setHighlighted((activeIndex - 1 + results.length) % Math.max(results.length, 1));
            }
            if (event.key === 'Home') {
              event.preventDefault();
              setHighlighted(0);
            }
            if (event.key === 'End') {
              event.preventDefault();
              setHighlighted(Math.max(results.length - 1, 0));
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

          <div className="relative flex items-center border-b border-border-default">
            <Search
              className="pointer-events-none absolute start-4 size-5 text-fg-muted"
              aria-hidden
            />
            <input
              autoFocus
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={open}
              aria-controls={listId}
              aria-activedescendant={activeId}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setHighlighted(0);
              }}
              placeholder={t('command.searchPlaceholder')}
              aria-label={t('command.searchAria')}
              dir="auto"
              className="selectable h-14 w-full bg-transparent pe-16 ps-12 text-body-lg text-fg-primary placeholder:text-fg-muted focus:outline-none"
            />
            <kbd className="ltr-island absolute end-4 rounded-md border border-border-default bg-surface-2 px-1.5 py-0.5 text-micro text-fg-muted">
              {t('command.hintClose')}
            </kbd>
          </div>

          <div id={listId} role="listbox" className="max-h-96 overflow-y-auto p-2">
            {results.length === 0 ? (
              <p
                role="status"
                aria-live="polite"
                className="px-3 py-10 text-center text-caption text-fg-muted"
              >
                {t('command.empty')}
              </p>
            ) : (
              results.map((command, index) => {
                const showCategory =
                  index === 0 || results[index - 1]?.category !== command.category;
                return (
                  <div key={command.id}>
                    {showCategory && (
                      <p className="px-3 pb-1 pt-2 text-micro font-semibold text-fg-muted">
                        {command.category}
                      </p>
                    )}
                    <button
                      id={`dream-command-${index}`}
                      role="option"
                      aria-selected={index === activeIndex}
                      type="button"
                      onPointerMove={() => setHighlighted(index)}
                      onClick={() => runCommand(command)}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-start text-body transition-colors duration-fast',
                        index === activeIndex
                          ? 'bg-accent-soft text-accent-text'
                          : 'text-fg-primary hover:bg-surface-2',
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate bidi-isolate">
                        {command.description}
                      </span>
                      {command.keys && (
                        <kbd className="ltr-island shrink-0 text-caption text-fg-muted">
                          {formatShortcut(command.keys)}
                        </kbd>
                      )}
                    </button>
                  </div>
                );
              })
            )}
          </div>
          <footer className="flex items-center gap-3 border-t border-border-default bg-surface-2 px-4 py-2 text-micro text-fg-muted">
            <span>{t('command.hintNavigate')}</span>
            <span>{t('command.hintRun')}</span>
            <span className="ms-auto">{t('command.count', { count: results.length })}</span>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
