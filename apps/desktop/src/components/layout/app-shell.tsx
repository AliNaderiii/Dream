/**
 * App shell: title bar → [activity rail | sidebar | workspace] → status bar.
 *
 * Mirrors automatically in RTL because every edge uses logical properties.
 */

import { useLocation, useMatch } from 'react-router-dom';
import { Outlet } from 'react-router-dom';

import { ActivityRail } from '@/components/layout/activity-rail';
import { BridgeDisconnectedBanner } from '@/components/bridge/bridge-disconnected-banner';
import { Sidebar } from '@/components/layout/sidebar';
import { StatusBar } from '@/components/layout/status-bar';
import { TitleBar } from '@/components/layout/title-bar';
import { TopBar } from '@/components/layout/top-bar';
import { CommandPalette } from '@/components/shared/command-palette';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useFileDrop } from '@/hooks/use-file-drop';
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { useNativeBridge } from '@/hooks/use-native-bridge';
import { useTheme } from '@/hooks/use-theme';
import { useLocaleSync, useTranslation } from '@/lib/i18n';

/** Pathname → common.nav key for the top-bar title. */
const NAV_SLUG: Record<string, string> = {
  '/': 'dashboard',
  '/projects': 'projects',
  '/scheduler': 'scheduler',
  '/memory': 'memory',
  '/skills': 'skills',
  '/subagents': 'subagents',
  '/data': 'data',
  '/provenance': 'provenance',
  '/providers': 'providers',
  '/settings': 'settings',
};

export function AppShell() {
  const { t } = useTranslation('common');
  const location = useLocation();
  const chatMatch = useMatch('/chat/:sessionId');

  useTheme();
  useLocaleSync();
  useNativeBridge();
  const shortcuts = useKeyboardShortcuts();
  const { isDragging } = useFileDrop();

  const title = chatMatch
    ? t('conversation')
    : t(`nav.${NAV_SLUG[location.pathname] ?? 'dashboard'}`);

  return (
    <TooltipProvider>
      <div className="surface-gradient flex h-screen flex-col overflow-hidden text-fg-primary">
        <TitleBar />

        <div className="flex min-h-0 flex-1">
          <ActivityRail />
          <Sidebar />

          <main className="relative flex min-w-0 flex-1 flex-col">
            <TopBar title={title} />
            <BridgeDisconnectedBanner />
            <div className="min-h-0 flex-1 overflow-y-auto">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </div>

            {/* Drop overlay: shown while files hover the window. */}
            {isDragging && (
              <div className="pointer-events-none absolute inset-0 z-40 m-3 flex items-center justify-center rounded-lg border-2 border-dashed border-accent bg-accent-soft/60">
                <p className="text-h3 font-semibold text-accent-text">{t('drop')}</p>
              </div>
            )}
          </main>
        </div>

        <StatusBar />
        <CommandPalette commands={shortcuts} />
      </div>
    </TooltipProvider>
  );
}
