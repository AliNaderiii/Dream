/**
 * Scheduler route (S06) — exposes the already-built schedule engine through
 * the echo transport: create from prose with a live Jalali preview, toggle,
 * history, and the fail-closed approval behaviour for dangerous runs.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { SchedulerRoute } from '@/routes/scheduler';

/** Persian (extended Arabic-Indic) digits — the Jalali calendar renders them. */
const PERSIAN_DIGITS = /[\u06F0-\u06F9]/;

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={['/scheduler']}>
      <SchedulerRoute />
    </MemoryRouter>,
  );
}

describe('SchedulerRoute (S06)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('shows the empty state before any schedule exists', async () => {
    renderRoute();
    expect(screen.getByRole('heading', { level: 2, name: 'Scheduler' })).toBeInTheDocument();
    expect(await screen.findByText('No scheduled tasks')).toBeInTheDocument();
  });

  it('creates a schedule from English prose with a Jalali preview', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New schedule' }));
    await user.type(await screen.findByLabelText('Name'), 'Morning brief');
    await user.type(screen.getByLabelText('Prompt'), 'summarise my day');
    await user.type(screen.getByLabelText('When'), 'every day at 9 AM');

    // Live preview: human reading, cron, and the Jalali next run.
    await screen.findByText('every day at 9:00 AM');
    expect(screen.getByText(/0 9 \* \* \*/)).toBeInTheDocument();
    const jalaliPreview = await screen.findByTestId('preview-jalali');
    expect(jalaliPreview.textContent).toMatch(PERSIAN_DIGITS);

    await user.click(screen.getByRole('button', { name: 'Create schedule' }));

    // The new job is listed with its description and Jalali next run.
    const card = await screen.findByRole('heading', { level: 3, name: 'Morning brief' });
    expect(card).toBeInTheDocument();
    expect(screen.getAllByText('every day at 9:00 AM').length).toBeGreaterThan(0);
    await waitFor(() => {
      const nextRunText = screen.getByText(/Next run/).parentElement?.textContent ?? '';
      expect(nextRunText).toMatch(PERSIAN_DIGITS);
    });
  });

  it('parses Persian prose too', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New schedule' }));
    await user.type(await screen.findByLabelText('Name'), 'مرور صبح');
    await user.type(screen.getByLabelText('Prompt'), 'خلاصه روز');
    await user.type(screen.getByLabelText('When'), 'هر روز ساعت ۹ صبح');

    await screen.findByText('every day at 9:00 AM');
    expect(screen.getByText(/0 9 \* \* \*/)).toBeInTheDocument();
  });

  it('toggles a schedule on and off', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New schedule' }));
    await user.type(await screen.findByLabelText('Name'), 'Hourly check');
    await user.type(screen.getByLabelText('Prompt'), 'check the feeds');
    await user.type(screen.getByLabelText('When'), 'every hour');
    await screen.findByText('at cron schedule 0 * * * *');
    await user.click(screen.getByRole('button', { name: 'Create schedule' }));
    await screen.findByRole('heading', { level: 3, name: 'Hourly check' });

    await user.click(screen.getByRole('button', { name: 'Pause: Hourly check' }));
    await screen.findByRole('button', { name: 'Enable: Hourly check' });
    // Both the status badge and the toggle button read "Paused" now.
    expect(screen.getAllByText('Paused').length).toBeGreaterThanOrEqual(1);
    await user.click(screen.getByRole('button', { name: 'Enable: Hourly check' }));
    await screen.findByRole('button', { name: 'Pause: Hourly check' });
  });

  it('fail-closed: an approval-required run is denied, never executed', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New schedule' }));
    await user.type(await screen.findByLabelText('Name'), 'Risky cleanup');
    await user.type(screen.getByLabelText('Prompt'), 'delete old files');
    await user.type(screen.getByLabelText('When'), 'every day at 3 AM');
    await screen.findByText(/0 3 \* \* \*/);
    await user.click(screen.getByLabelText(/Require approval before each run/));
    await user.click(screen.getByRole('button', { name: 'Create schedule' }));
    await screen.findByRole('heading', { level: 3, name: 'Risky cleanup' });

    // The badge marks the job as approval-gated.
    expect(screen.getByText('Approval required')).toBeInTheDocument();

    // Running it now records a denial — the echo has no approver, and the
    // policy is fail-closed: no approval, no run.
    await user.click(screen.getByRole('button', { name: 'Run now' }));
    await user.click(await screen.findByRole('button', { name: /History/ }));
    expect(await screen.findByText('approval denied')).toBeInTheDocument();
  });

  it('deletes a schedule only after confirmation', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New schedule' }));
    await user.type(await screen.findByLabelText('Name'), 'Doomed');
    await user.type(screen.getByLabelText('Prompt'), 'gone soon');
    await user.type(screen.getByLabelText('When'), 'every hour');
    await screen.findByText('at cron schedule 0 * * * *');
    await user.click(screen.getByRole('button', { name: 'Create schedule' }));
    await screen.findByRole('heading', { level: 3, name: 'Doomed' });

    await user.click(screen.getByRole('button', { name: 'Delete: Doomed' }));
    expect(screen.getByText('Delete this schedule?')).toBeInTheDocument();
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 3, name: 'Doomed' })).toBeNull();
    });
  });
});
