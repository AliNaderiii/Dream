import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';

import App from '@/App';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { applyAppearance } from '@/hooks/use-theme';
import { initI18n, resolveInitialLocale } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import '@/styles/theme.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root is missing from index.html');

// Seed the store (locale + direction) with the detected or persisted locale
// before the first render, then initialise i18next to match.
const initialLocale = resolveInitialLocale();
useAppStore.getState().setLocale(initialLocale);
const initialAppearance = useAppStore.getState();
applyAppearance(initialAppearance);

void (async () => {
  await initI18n(initialLocale);

  // HashRouter, not BrowserRouter: bundled Tauri apps are served from the
  // `tauri://localhost` asset protocol, where path-based routing cannot deep-link.
  createRoot(container).render(
    <StrictMode>
      <ErrorBoundary>
        <HashRouter>
          <App />
        </HashRouter>
      </ErrorBoundary>
    </StrictMode>,
  );
})();
