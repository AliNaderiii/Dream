/** Virtual screens and the active screen's recursive pane tree. */

import { Monitor, Plus, RotateCcw, X } from 'lucide-react';
import { useEffect } from 'react';

import { Pane, PANE_DRAG_TYPE } from '@/components/panes/pane';
import { SplitLayout } from '@/components/panes/split-layout';
import { Button } from '@/components/ui/button';
import { findPane, useLayoutStore } from '@/stores/use-layout-store';
import { useProviderStore } from '@/stores/use-provider-store';
import { cn } from '@/utils/cn';

export function PaneWorkspace() {
  const screens = useLayoutStore((state) => state.screens);
  const activeScreenId = useLayoutStore((state) => state.activeScreenId);
  const setActiveScreen = useLayoutStore((state) => state.setActiveScreen);
  const addScreen = useLayoutStore((state) => state.addScreen);
  const renameScreen = useLayoutStore((state) => state.renameScreen);
  const removeScreen = useLayoutStore((state) => state.removeScreen);
  const movePaneToScreen = useLayoutStore((state) => state.movePaneToScreen);
  const closePane = useLayoutStore((state) => state.closePane);
  const toggleMaximize = useLayoutStore((state) => state.toggleMaximize);
  const resetLayout = useLayoutStore((state) => state.resetLayout);
  const loadProviders = useProviderStore((state) => state.load);
  const activeScreen = screens.find((screen) => screen.id === activeScreenId) ?? screens[0];

  useEffect(() => {
    void loadProviders();
  }, [loadProviders]);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((!event.metaKey && !event.ctrlKey) || !activeScreen) return;
      const typing = (event.target as HTMLElement | null)?.matches(
        'input, textarea, select, [contenteditable]',
      );
      if (typing) return;
      if (event.key.toLowerCase() === 'w' && !event.shiftKey) {
        event.preventDefault();
        closePane(activeScreen.activePaneId);
      }
      if (event.key.toLowerCase() === 'm' && event.shiftKey) {
        event.preventDefault();
        toggleMaximize(activeScreen.activePaneId);
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [activeScreen, closePane, toggleMaximize]);

  if (!activeScreen) {
    return (
      <div className="flex size-full items-center justify-center">
        <Button onClick={resetLayout}>
          <RotateCcw aria-hidden /> Restore workspace
        </Button>
      </div>
    );
  }

  const maximized = activeScreen.maximizedPaneId
    ? findPane(activeScreen.root, activeScreen.maximizedPaneId)
    : undefined;

  return (
    <div className="flex size-full min-h-0 flex-col bg-sunken">
      <nav
        aria-label="Screens"
        className="flex h-9 shrink-0 items-end gap-0.5 overflow-x-auto border-b border-border-default bg-surface px-2 pt-1"
      >
        {screens.map((screen) => (
          <button
            key={screen.id}
            type="button"
            onClick={() => setActiveScreen(screen.id)}
            onDoubleClick={() => {
              const name = window.prompt('Rename screen', screen.name);
              if (name) renameScreen(screen.id, name);
            }}
            onDragOver={(event) => {
              if (event.dataTransfer.types.includes(PANE_DRAG_TYPE)) event.preventDefault();
            }}
            onDrop={(event) => {
              event.preventDefault();
              const paneId = event.dataTransfer.getData(PANE_DRAG_TYPE);
              if (paneId) movePaneToScreen(paneId, screen.id);
            }}
            className={cn(
              'group flex h-8 min-w-28 items-center gap-2 rounded-t-md border border-b-0 px-3 text-caption transition-colors',
              screen.id === activeScreen.id
                ? 'border-border-default bg-canvas text-fg-primary'
                : 'border-transparent text-fg-secondary hover:bg-surface-2 hover:text-fg-primary',
            )}
          >
            <span className="min-w-0 flex-1 truncate">{screen.name}</span>
            {screens.length > 1 && (
              <span
                role="button"
                tabIndex={0}
                aria-label={`Close ${screen.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  removeScreen(screen.id);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') removeScreen(screen.id);
                }}
                className="rounded-xs p-0.5 opacity-0 hover:bg-sunken group-hover:opacity-100 focus:opacity-100"
              >
                <X className="size-3" aria-hidden />
              </span>
            )}
          </button>
        ))}
        <Button
          variant="ghost"
          size="icon-sm"
          className="mb-0.5 size-7 shrink-0"
          aria-label="New screen"
          title="New virtual screen"
          onClick={() => addScreen()}
        >
          <Plus aria-hidden />
        </Button>
        <span className="ms-auto mb-1 hidden items-center gap-1 text-micro text-fg-muted lg:flex">
          <Monitor className="size-3" aria-hidden />
          Drag a pane here to move screens
        </span>
      </nav>

      <div className="min-h-0 flex-1 p-1">
        {maximized ? (
          <Pane pane={maximized} active />
        ) : (
          <SplitLayout node={activeScreen.root} activePaneId={activeScreen.activePaneId} />
        )}
      </div>
    </div>
  );
}
