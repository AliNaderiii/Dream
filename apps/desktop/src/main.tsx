import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';

import App from '@/App';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import '@/styles/theme.css';

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root is missing from index.html');

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
