/**
 * Settings — appearance and window behaviour are live in P-01; the remaining
 * categories arrive with the features they configure.
 */

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { dialogApi, windowApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import type { Density, Locale, ThemeMode } from '@/types';

/** A labelled settings row. */
function Row({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-border-default py-3 last:border-b-0">
      <div className="min-w-0">
        <p className="text-body font-medium">{label}</p>
        {description && <p className="text-caption text-fg-secondary">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const THEMES: ThemeMode[] = ['light', 'dark', 'system'];
const DENSITIES: Density[] = ['comfortable', 'compact'];
const LOCALES: Array<{ value: Locale; label: string }> = [
  { value: 'en', label: 'English' },
  { value: 'fa', label: 'فارسی' },
];

export function SettingsRoute() {
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const density = useAppStore((s) => s.density);
  const setDensity = useAppStore((s) => s.setDensity);
  const locale = useAppStore((s) => s.locale);
  const setLocale = useAppStore((s) => s.setLocale);
  const workspaceRoot = useAppStore((s) => s.workspaceRoot);
  const setWorkspaceRoot = useAppStore((s) => s.setWorkspaceRoot);

  const [minimizeToTray, setMinimizeToTray] = useState(false);
  const [closeToTray, setCloseToTray] = useState(true);

  // Push window-behaviour preferences down to Rust whenever they change.
  useEffect(() => {
    void windowApi.setMinimizeToTray(minimizeToTray);
  }, [minimizeToTray]);

  useEffect(() => {
    void windowApi.setCloseToTray(closeToTray);
  }, [closeToTray]);

  const chooseWorkspace = async () => {
    const folder = await dialogApi.selectFolder({ title: 'Choose workspace folder' });
    if (!folder) return;
    await dialogApi.setWorkspaceRoot(folder);
    setWorkspaceRoot(folder);
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8 p-8">
      <section>
        <h2 className="pb-2 text-h2 font-semibold">Appearance</h2>

        <Row label="Theme" description="Follows your system setting unless overridden.">
          <div className="flex gap-1">
            {THEMES.map((option) => (
              <Button
                key={option}
                size="sm"
                variant={theme === option ? 'primary' : 'secondary'}
                onClick={() => setTheme(option)}
              >
                {option}
              </Button>
            ))}
          </div>
        </Row>

        <Row label="Density" description="Compact reduces component padding by 25%.">
          <div className="flex gap-1">
            {DENSITIES.map((option) => (
              <Button
                key={option}
                size="sm"
                variant={density === option ? 'primary' : 'secondary'}
                onClick={() => setDensity(option)}
              >
                {option}
              </Button>
            ))}
          </div>
        </Row>

        <Row label="Language" description="Persian switches the whole shell to right-to-left.">
          <div className="flex gap-1">
            {LOCALES.map((option) => (
              <Button
                key={option.value}
                size="sm"
                variant={locale === option.value ? 'primary' : 'secondary'}
                onClick={() => setLocale(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </Row>
      </section>

      <section>
        <h2 className="pb-2 text-h2 font-semibold">Window</h2>

        <Row label="Minimize to tray" description="Hide the window instead of minimizing it.">
          <Button
            size="sm"
            variant={minimizeToTray ? 'primary' : 'secondary'}
            aria-pressed={minimizeToTray}
            onClick={() => setMinimizeToTray((v) => !v)}
          >
            {minimizeToTray ? 'On' : 'Off'}
          </Button>
        </Row>

        <Row
          label="Close to tray"
          description="Keep Dream running in the tray when the window closes."
        >
          <Button
            size="sm"
            variant={closeToTray ? 'primary' : 'secondary'}
            aria-pressed={closeToTray}
            onClick={() => setCloseToTray((v) => !v)}
          >
            {closeToTray ? 'On' : 'Off'}
          </Button>
        </Row>
      </section>

      <section>
        <h2 className="pb-2 text-h2 font-semibold">Workspace</h2>

        <Row
          label="Workspace folder"
          description={workspaceRoot ?? 'No folder selected — file access is unrestricted.'}
        >
          <Button size="sm" onClick={() => void chooseWorkspace()}>
            Choose…
          </Button>
        </Row>
      </section>
    </div>
  );
}
