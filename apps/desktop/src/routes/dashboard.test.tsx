/**
 * Tests for the DashboardRoute (S15).
 *
 * Verifies that the dashboard renders without throwing.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DashboardRoute } from '@/routes/dashboard';
import { resetBridgeClient } from '@/lib/bridge/client';

// Mock the session store
vi.mock('@/stores/use-session-store', () => ({
  useSessionStore: vi.fn((selector) => {
    const store = {
      sessions: [],
      createSession: vi.fn(() => ({ id: 'test-session-123' })),
    };
    return selector(store);
  }),
}));

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <DashboardRoute />
    </MemoryRouter>,
  );
}

describe('DashboardRoute (S15)', () => {
  beforeEach(() => {
    resetBridgeClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the dashboard without throwing', () => {
    // The dashboard should render without crashing, even when icons are loaded.
    const { container } = renderDashboard();
    expect(container).toBeTruthy();
  });

  it('shows the greeting heading', () => {
    renderDashboard();
    expect(screen.getByRole('heading', { level: 2 })).toBeTruthy();
  });

  it('renders without crashing regardless of bridge state', () => {
    // Even if the bridge is in any state, the dashboard should render
    const { container } = renderDashboard();
    expect(container.innerHTML).toContain('button');
  });
});

describe('SafeIcon utility', () => {
  it('returns null for non-function values', async () => {
    const { SafeIcon } = await import('@/utils/icons');

    const { container } = render(<SafeIcon icon={undefined as never} className="test" />);
    expect(container.innerHTML).toBe('');
  });

  it('returns null for null values', async () => {
    const { SafeIcon } = await import('@/utils/icons');

    const { container } = render(<SafeIcon icon={null as never} className="test" />);
    expect(container.innerHTML).toBe('');
  });

  it('returns null for string values', async () => {
    const { SafeIcon } = await import('@/utils/icons');

    const { container } = render(<SafeIcon icon={'not a function' as never} className="test" />);
    expect(container.innerHTML).toBe('');
  });

  it('returns null for undefined icon (defensive)', async () => {
    const { SafeIcon } = await import('@/utils/icons');

    const { container } = render(<SafeIcon icon={undefined} className="size-5" aria-hidden />);
    expect(container.innerHTML).toBe('');
  });
});
