/**
 * Custom title bar.
 *
 * macOS keeps its native traffic lights (the window uses an overlay title bar),
 * so only padding is reserved for them. Windows and Linux get drawn controls.
 * The whole bar is a drag region except for interactive controls.
 */

import { Maximize2, Minus, Square, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { windowApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import { cn } from '@/utils/cn';
import { isMacOS } from '@/utils/platform';

/** Height must match `--spacing-titlebar`. */
export function TitleBar() {
  const { t } = useTranslation('common');
  const mac = isMacOS();
  const [maximized, setMaximized] = useState(false);
  const pendingApprovals = useAppStore((s) => s.pendingApprovals);

  // Keep the maximise glyph in sync when the OS changes the state for us
  // (double-click on the bar, window snapping, keyboard shortcuts).
  useEffect(() => {
    const onResize = () => {
      setMaximized(
        window.outerWidth >= screen.availWidth - 8 && window.outerHeight >= screen.availHeight - 8,
      );
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <header
      data-tauri-drag-region
      className={cn(
        'drag-region flex h-titlebar shrink-0 items-center justify-between border-b border-border-default bg-surface-raised',
        // Reserve room for macOS traffic lights, which sit at the inline start.
        mac ? 'ps-mac-controls pe-3' : 'ps-3 pe-0',
      )}
    >
      <div
        data-tauri-drag-region
        className="flex items-center gap-2 text-caption text-fg-secondary"
      >
        <span data-tauri-drag-region className="font-semibold text-fg-primary">
          Dream
        </span>
        {pendingApprovals > 0 && (
          <span className="rounded-full bg-warning-bg px-1.5 py-0.5 text-micro font-semibold text-warning-fg">
            {t('titlebar.pending', { count: pendingApprovals })}
          </span>
        )}
      </div>

      {!mac && (
        <div className="no-drag flex items-center">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('titlebar.minimize')}
            className="h-titlebar w-11 rounded-none"
            onClick={() => void windowApi.minimize()}
          >
            <Minus aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={maximized ? t('titlebar.restore') : t('titlebar.maximize')}
            className="h-titlebar w-11 rounded-none"
            onClick={() => void windowApi.toggleMaximize().then((v) => setMaximized(Boolean(v)))}
          >
            {maximized ? <Square aria-hidden /> : <Maximize2 aria-hidden />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('titlebar.close')}
            className="h-titlebar w-11 rounded-none hover:bg-danger-fg hover:text-surface"
            onClick={() => void windowApi.close()}
          >
            <X aria-hidden />
          </Button>
        </div>
      )}
    </header>
  );
}
