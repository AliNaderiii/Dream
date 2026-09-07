/**
 * App shell: title bar -> [activity rail | sidebar | workspace] -> status bar.
 *
 * Mirrors automatically in RTL because every edge uses logical properties.
 *
 * At narrow viewports the shell switches to a mobile-friendly layout:
 *   - Tauri window controls are hidden when there is no Tauri backend.
 *   - Activity rail collapses to icon-only at phone breakpoints; a bottom nav
 *     bar carries the primary destinations on phones.
 *   - Sidebar becomes a drawer at narrow widths; the desktop resizable panel
 *     is preserved at wide widths.
 *   - TopBar secondary actions move behind an overflow menu at narrow widths.
 *   - StatusBar wraps at narrow widths.
 */

import { lazy, Suspense } from 'react';
import { useLocation, useMatch, useNavigate } from 'react-router-dom';
import { Outlet } from 'react-router-dom';

import { ActivityRail } from '@/components/layout/activity-rail';
import { BottomNav } from '@/components/responsive/bottom-nav';
import { BridgeDisconnectedBanner } from '@/components/bridge/bridge-disconnected-banner';
import { Sidebar } from '@/components/layout/sidebar';
import { SidebarDrawer } from '@/components/responsive/sidebar-drawer';
import { StatusBar } from '@/components/layout/status-bar';
import { TitleBar } from '@/components/layout/title-bar';
import { TopBar } from '@/components/layout/top-bar';
import { CommandPalette } from '@/components/shared/command-palette';
import { SessionSearch } from '@/components/search/session-search';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useFileDrop } from '@/hooks/use-file-drop';
import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { useNativeBridge } from '@/hooks/use-native-bridge';
import { useTheme } from '@/hooks/use-theme';
import { isDrawerBreakpoint, useViewport } from '@/hooks/use-viewport';
import { useLocaleSync, useTranslation } from '@/lib/i18n';
import { registeredRoutes } from '@/lib/route-registry';

// The off-mode security banner is always mounted but lives in its own chunk;
// it renders nothing unless the engine reports approvals off.
const SecurityOffBanner = lazy(() =>
  import('@/components/security/security-off-banner').then((m) => ({
    default: m.SecurityOffBanner,
  })),
);

/** Pathname -> common.nav key for the top-bar title. */
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
  const navigate = useNavigate();
  const chatMatch = useMatch('/chat/:sessionId');
  const viewport = useViewport();

  useTheme();
  useLocaleSync();
  useNativeBridge();
  const shortcuts = useKeyboardShortcuts();
  const { isDragging } = useFileDrop();

  // P0 SEAM: extension route labels are i18n keys just like built-in nav labels.
  const extensionLabel = registeredRoutes.find((route) => route.path === location.pathname)?.label;
  const title = chatMatch
    ? t('conversation')
    : extensionLabel
      ? t(extensionLabel)
      : t(`nav.${NAV_SLUG[location.pathname] ?? 'dashboard'}`);

  const isPhone = viewport.breakpoint === 'phonePortrait' || viewport.breakpoint === 'phoneLandscape';
  const showBottomNav = isPhone;
  const atDrawerBreakpoint = isDrawerBreakpoint(viewport.breakpoint);
  const showSidebarDrawer = atDrawerBreakpoint;

  return (
    <TooltipProvider>
      <div className="surface-gradient flex h-screen flex-col overflow-hidden text-fg-primary">
        <TitleBar />

        <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
          <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
            {isPhone ? null : <ActivityRail />}
            {showSidebarDrawer ? (
              <SidebarDrawer />
            ) : (
              <Sidebar />
            )}

            <main className="relative flex min-w-0 flex-1 flex-col">
              <TopBar title={title} />
              <BridgeDisconnectedBanner />
              <Suspense fallback={null}>
                <SecurityOffBanner />
              </Suspense>
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

          {/* Bottom navigation: phone breakpoints only. */}
          {showBottomNav && <BottomNav />}
        </div>

        <StatusBar />
        <CommandPalette
          commands={shortcuts}
          onOpenSession={(sessionId) => void navigate(`/chat/${sessionId}`)}
        />
        <SessionSearch onOpenSession={(sessionId) => void navigate(`/chat/${sessionId}`)} />
      </div>
    </TooltipProvider>
  );
}
