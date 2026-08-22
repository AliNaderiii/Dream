import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { TooltipProvider } from '../src/components/ui/tooltip';
import { initI18n } from '../src/lib/i18n';
import '../src/styles/theme.css';

void initI18n('en');

export const Provider = ({ children }: { children: ReactNode }) => (
  <MemoryRouter>
    <TooltipProvider>{children}</TooltipProvider>
  </MemoryRouter>
);
