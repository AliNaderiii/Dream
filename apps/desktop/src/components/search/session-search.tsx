/**
 * Session search dialog (MEM Stage F): Ctrl/Cmd+P across every past
 * conversation.
 *
 * Laws pinned by the tests:
 *
 * - Persian matching is spelling-insensitive through the shared normalizer,
 *   and the highlight keeps the *user's own* spelling — parsed from the
 *   kernel's `[...]` snippet markers into text segments rendered as
 *   `<mark>`, never as markup;
 * - a damaged index is said out loud (the refusal is rendered, reads stay
 *   refused) and offers a rebuild that recovers;
 * - an empty result set is not a failure (no `role="alert"`);
 * - while the bridge is offline the rebuild control disables.
 */

import * as Dialog from '@radix-ui/react-dialog';
import { Search } from 'lucide-react';
import { useEffect } from 'react';

import { VirtualList } from '@/components/shared/virtual-list';
import { Button } from '@/components/ui/button';
import { parseSnippet } from '@/components/search/snippet-model';
import { useSessionSearch } from '@/components/search/use-session-search';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import { formatShortcut } from '@/utils/platform';

export interface SessionSearchProps {
  /** Opens one conversation; wired by the shell, never from inside. */
  onOpenSession?: (sessionId: string) => void;
}

export function SessionSearch({ onOpenSession }: SessionSearchProps) {
  const { t } = useTranslation('search');
  const { state } = useBridge();
  const offline = state === 'disconnected';
  const open = useAppStore((store) => store.sessionSearchOpen);
  const setOpen = useAppStore((store) => store.setSessionSearchOpen);
  const search = useSessionSearch(open);

  // Closing the dialog resets the query through the hook's open dependency.
  useEffect(() => {
    if (!open) search.runQuery('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const openSession = (sessionId: string) => {
    setOpen(false);
    onOpenSession?.(sessionId);
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="motion-enter fixed inset-0 z-50 bg-black/40 motion-reduce:animate-none" />
        <Dialog.Content
          aria-label={t('title')}
          className="motion-enter fixed start-1/2 top-16 z-50 flex max-h-[70vh] w-[min(var(--overlay-lg),92vw)] -translate-x-1/2 flex-col overflow-hidden rounded-2xl border border-border-default bg-overlay shadow-e3 rtl:translate-x-1/2"
        >
          <Dialog.Title className="sr-only">{t('title')}</Dialog.Title>
          <Dialog.Description className="sr-only">{t('description')}</Dialog.Description>

          <div className="relative flex items-center border-b border-border-default">
            <Search
              className="pointer-events-none absolute start-4 size-5 text-fg-muted"
              aria-hidden
            />
            <input
              type="search"
              autoFocus
              value={search.query}
              onChange={(event) => search.runQuery(event.target.value)}
              placeholder={t('placeholder')}
              aria-label={t('inputAria')}
              dir="auto"
              className="h-14 w-full bg-transparent pe-16 ps-12 text-body-lg text-fg-primary placeholder:text-fg-muted focus:outline-none"
            />
            <kbd className="ltr-island absolute end-4 rounded-md border border-border-default bg-surface-2 px-1.5 py-0.5 text-micro text-fg-muted">
              {formatShortcut(['mod', 'p'])}
            </kbd>
          </div>

          <p
            className="flex items-center gap-2 border-b border-border-default bg-surface-2 px-4 py-1.5 text-micro text-fg-muted"
            role="status"
          >
            {search.status === null
              ? t('status.checking')
              : search.status.healthy
                ? t('status.healthy', { count: search.status.documents })
                : t('status.unhealthy')}
            {search.searching && <span aria-live="polite">{t('searching')}</span>}
          </p>

          {search.refusal && (
            <div
              role="alert"
              className="flex items-center gap-3 border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg"
            >
              <span className="min-w-0 flex-1 bidi-isolate" dir="auto">
                {search.refusal}
              </span>
              <Button
                size="sm"
                variant="secondary"
                disabled={offline || search.rebuilding}
                onClick={() => void search.rebuild()}
              >
                {search.rebuilding ? t('status.rebuilding') : t('status.rebuild')}
              </Button>
            </div>
          )}
          {search.error && !search.refusal && (
            <p
              role="alert"
              className="border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg bidi-isolate"
              dir="auto"
            >
              {search.error}
            </p>
          )}

          <div className="min-h-0 flex-1 overflow-hidden p-2">
            {search.results.length === 0 ? (
              <p
                role="status"
                aria-live="polite"
                className="px-3 py-10 text-center text-caption text-fg-muted"
              >
                {search.searching ? t('searching') : t('empty')}
              </p>
            ) : (
              <VirtualList
                items={search.results}
                getKey={(hit) => hit.session_id}
                estimateSize={76}
                virtualizeAt={0}
                ariaLabel={t('resultsLabel')}
                className="max-h-full"
                renderItem={(hit) => (
                  <div className="h-full py-1">
                    <button
                      type="button"
                      aria-current={false}
                      onClick={() => openSession(hit.session_id)}
                      className="flex w-full flex-col gap-1 rounded-lg px-3 py-2 text-start transition-colors duration-fast hover:bg-surface-2 motion-reduce:transition-none"
                    >
                      <span className="flex items-center gap-2">
                        <span
                          className="min-w-0 flex-1 truncate text-body font-medium text-fg-primary bidi-isolate"
                          dir="auto"
                        >
                          {hit.title}
                        </span>
                        {hit.matched_in_title && (
                          <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-micro text-accent-text">
                            {t('matchedInTitle')}
                          </span>
                        )}
                      </span>
                      <span
                        className="line-clamp-2 text-caption text-fg-secondary bidi-isolate"
                        dir="auto"
                      >
                        {parseSnippet(hit.snippet).map((segment, index) =>
                          segment.highlight ? (
                            <mark
                              key={index}
                              className="rounded-sm bg-accent-soft text-accent-text"
                            >
                              {segment.text}
                            </mark>
                          ) : (
                            <span key={index}>{segment.text}</span>
                          ),
                        )}
                      </span>
                    </button>
                  </div>
                )}
              />
            )}
          </div>

          <footer className="flex items-center gap-3 border-t border-border-default bg-surface-2 px-4 py-2 text-micro text-fg-muted">
            <span>{t('prompt')}</span>
            <span className="ms-auto">{t('count', { rows: search.results.length })}</span>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
