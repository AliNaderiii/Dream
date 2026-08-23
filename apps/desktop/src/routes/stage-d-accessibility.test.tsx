import axe from 'axe-core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { Sidebar } from '@/components/layout/sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import { resetBridgeClient } from '@/lib/bridge/client';
import { MemoryRoute } from '@/routes/memory';
import { SchedulerRoute } from '@/routes/scheduler';
import { SkillsRoute } from '@/routes/skills';
import { SubagentsRoute } from '@/routes/subagents';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';

async function expectNoViolations(container: HTMLElement, surface: string) {
  const report = await axe.run(container, {
    rules: {
      // jsdom has no paint engine; source-token contrast is enforced separately.
      'color-contrast': { enabled: false },
    },
  });
  console.info(`axe_surface=${surface} violations=${report.violations.length}`);
  expect(report.violations).toEqual([]);
}

function SurfaceFrame({ children, title }: { children: ReactNode; title: string }) {
  return (
    <main>
      <h1 className="sr-only">{title}</h1>
      {children}
    </main>
  );
}

describe('Stage D surface accessibility', () => {
  beforeEach(() => {
    resetBridgeClient();
    useAppStore.setState({ sidebarCollapsed: false });
    useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
  });

  it('has no axe violations in the session manager', async () => {
    const { container } = render(
      <MemoryRouter>
        <TooltipProvider>
          <SurfaceFrame title="Session manager">
            <Sidebar />
          </SurfaceFrame>
        </TooltipProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('No sessions yet. Start one to begin.')).toBeInTheDocument();
    await expectNoViolations(container, 'sessions');
  });

  it('has no axe violations in the memory explorer', async () => {
    const { container } = render(
      <SurfaceFrame title="Memory explorer audit">
        <MemoryRoute />
      </SurfaceFrame>,
    );
    await screen.findByText(/Dream stores memories as semantic/);
    await expectNoViolations(container, 'memory');
  });

  it('has no axe violations in the memory bounded stores panel', async () => {
    const { container } = render(
      <SurfaceFrame title="Bounded stores audit">
        <MemoryRoute />
      </SurfaceFrame>,
    );
    await screen.findByText(/Dream stores memories as semantic/);
    fireEvent.click(screen.getByRole('tab', { name: 'Bounded stores' }));
    await screen.findByText(/frozen at session start/i);
    await expectNoViolations(container, 'memory-bounded');
  });

  it('has no axe violations in the skills manager', async () => {
    const { container } = render(
      <SurfaceFrame title="Skills manager audit">
        <SkillsRoute />
      </SurfaceFrame>,
    );
    await screen.findByText('weekly report');
    await expectNoViolations(container, 'skills');
  });

  it('has no axe violations in the subagent dashboard', async () => {
    const { container } = render(
      <SurfaceFrame title="Subagent dashboard audit">
        <SubagentsRoute />
      </SurfaceFrame>,
    );
    await screen.findByText('No subagents yet');
    await expectNoViolations(container, 'subagents');
  });

  it('has no axe violations in the scheduler', async () => {
    const { container } = render(
      <SurfaceFrame title="Scheduler audit">
        <SchedulerRoute />
      </SurfaceFrame>,
    );
    await screen.findByText('No scheduled tasks');
    await expectNoViolations(container, 'scheduler');
  });
});
