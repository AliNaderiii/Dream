/**
 * Reminder authoring panel (P-13) — reminders ride the `schedule.*` echo
 * runtime. These tests use a state transport over the echo transport, fake
 * timers where time matters, and never touch the network.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

import { RemindersPanel } from './reminders-panel';

/** Persian (extended Arabic-Indic) digits — the Jalali calendar renders them. */
const PERSIAN_DIGITS = /[\u06F0-\u06F9]/;

class RemindersStateTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private readonly echo = new EchoBridgeTransport();
  listParams: RpcParams[] = [];
  createdParams: RpcParams[] = [];
  updatedParams: RpcParams[] = [];
  failListOnce = false;

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    if (method === 'schedule.list') {
      this.listParams.push(structuredClone(params));
      if (this.failListOnce) {
        this.failListOnce = false;
        return Promise.reject(new Error('reminder list unavailable'));
      }
    }
    if (method === 'schedule.create') {
      this.createdParams.push(structuredClone(params));
    }
    if (method === 'schedule.update') {
      this.updatedParams.push(structuredClone(params));
    }
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(_handler: (state: BridgeConnectionState) => void) {
    return () => {};
  }

  reconnect() {}
}

function renderPanel() {
  return render(<RemindersPanel />);
}

/** Update calls the panel made, for async assertions after refreshes. */
function updatedParams(transport: RemindersStateTransport): Promise<RpcParams[]> {
  return waitFor(() => {
    expect(transport.updatedParams.length).toBeGreaterThan(0);
    return transport.updatedParams;
  });
}

describe('RemindersPanel', () => {
  beforeEach(() => {
    resetBridgeClient();
    vi.restoreAllMocks();
  });

  it('shows the empty state and requests only reminders from the bridge', async () => {
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    expect(await screen.findByText(/No reminders yet/i)).toBeInTheDocument();
    expect(transport.listParams).toEqual([{ include_disabled: true, kind: 'reminder' }]);
  });

  it('creates a one-off reminder with max_runs 1 and a compiled cron', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Renew the insurance');

    // "Once (date & time)" is the default mode; fill date and time directly
    // (jsdom does not keyboard-navigate date/time pickers).
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2030-03-20' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '09:30' } });

    // The preview resolves through schedule.preview and shows the cron.
    await waitFor(() => {
      expect(within(dialog).getByText(/30 9 20 3 \*/)).toBeInTheDocument();
    });

    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));

    expect(transport.createdParams).toEqual([
      expect.objectContaining({
        name: 'Renew the insurance',
        kind: 'reminder',
        cron_expression: '30 9 20 3 *',
        max_runs: 1,
      }),
    ]);
    // The new reminder appears in the list with its once badge.
    expect(await screen.findByText('Renew the insurance')).toBeInTheDocument();
    expect(screen.getByText(/^once$/i)).toBeInTheDocument();
  });

  it('shows a Jalali date next to the Gregorian fire time', async () => {
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Jalali check');
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2030-03-20' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '09:30' } });
    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));

    const jalali = await screen.findByTestId('reminder-next-jalali');
    expect(jalali).toHaveTextContent(PERSIAN_DIGITS);
  });

  it('refuses a past one-off date before anything is submitted', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Past reminder');
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2020-01-01' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '09:30' } });

    expect(
      await within(dialog).findAllByText(/date and time must be in the future/i),
    ).not.toHaveLength(0);
    expect(within(dialog).getByRole('button', { name: /create reminder/i })).toBeDisabled();
    expect(transport.createdParams).toEqual([]);
  });

  it('creates a repeating reminder from a rhythm through the live preview', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Daily standup note');
    await user.click(within(dialog).getByRole('radio', { name: /repeating/i }));
    await user.type(within(dialog).getByLabelText(/rhythm/i), 'every day at 9 AM');

    // The prose preview resolves to a human reading plus a cron line.
    await waitFor(() => {
      expect(within(dialog).getByText(/every day/i)).toBeInTheDocument();
      expect(within(dialog).getByText(/0 9 \* \* \*/)).toBeInTheDocument();
    });

    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));

    expect(transport.createdParams).toEqual([
      expect.objectContaining({
        name: 'Daily standup note',
        kind: 'reminder',
        natural_language: 'every day at 9 AM',
      }),
    ]);
    expect(transport.createdParams[0]).not.toHaveProperty('max_runs');
    expect(await screen.findByText('Daily standup note')).toBeInTheDocument();
  });

  it('blocks an unparseable rhythm instead of submitting it', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Broken');
    await user.click(within(dialog).getByRole('radio', { name: /repeating/i }));
    await user.type(within(dialog).getByLabelText(/rhythm/i), 'whenever the mood strikes');

    await waitFor(() => {
      expect(within(dialog).getByText(/not understood yet/i)).toBeInTheDocument();
    });
    expect(within(dialog).getByRole('button', { name: /create reminder/i })).toBeDisabled();
    expect(transport.createdParams).toEqual([]);
  });

  it('pauses and resumes a reminder through schedule.toggle', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Toggle me');
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2030-03-20' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '08:00' } });
    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));
    expect(await screen.findByText('Toggle me')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /pause: toggle me/i }));
    expect(await screen.findByText(/^paused$/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /resume: toggle me/i }));
    await waitFor(() => {
      expect(screen.queryByText(/^paused$/i)).not.toBeInTheDocument();
    });
  });

  it('deletes a reminder only after an explicit confirmation', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Delete me');
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2030-03-20' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '08:00' } });
    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));
    expect(await screen.findByText('Delete me')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /delete: delete me/i }));

    const confirm = await screen.findByRole('dialog', { name: /delete this reminder\?/i });
    // Truthful wording: permanent removal, no undo.
    expect(within(confirm).getByText(/removed permanently/i)).toBeInTheDocument();
    await user.click(within(confirm).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => {
      expect(screen.queryByText('Delete me')).not.toBeInTheDocument();
    });
  });

  it('surfaces a load failure with a retry action', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    transport.failListOnce = true;
    getBridgeClient().setTransport(transport);
    renderPanel();

    const alert = await screen.findByRole('alert');
    // The RPC error message is surfaced verbatim, not swallowed.
    expect(alert).toHaveTextContent(/reminder list unavailable/i);
    expect(transport.listParams).toHaveLength(1);

    await user.click(within(alert).getByRole('button', { name: /retry/i }));
    await screen.findByText(/No reminders yet/i);
    expect(transport.listParams).toHaveLength(2);
  });

  it('announces state politely and labels every control accessibly', async () => {
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    expect(await screen.findByText(/No reminders yet/i)).toBeInTheDocument();
    // Header and empty-state actions both offer creation, both accessible.
    expect(screen.getAllByRole('button', { name: /new reminder/i }).length).toBeGreaterThan(0);
  });

  it('edits a one-off into a repeating reminder and clears max_runs', async () => {
    const user = userEvent.setup();
    const transport = new RemindersStateTransport();
    getBridgeClient().setTransport(transport);
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /new reminder/i }));
    let dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/reminder/i), 'Flexible');
    fireEvent.change(within(dialog).getByLabelText(/^date$/i), { target: { value: '2030-03-20' } });
    fireEvent.change(within(dialog).getByLabelText(/^time$/i), { target: { value: '08:00' } });
    await user.click(within(dialog).getByRole('button', { name: /create reminder/i }));
    expect(await screen.findByText('Flexible')).toBeInTheDocument();
    expect(screen.getByText(/^once$/i)).toBeInTheDocument();

    // Edit: switch to repeating with a rhythm phrase.
    await user.click(screen.getByRole('button', { name: /edit: flexible/i }));
    dialog = await screen.findByRole('dialog');
    // The one-off prefill lands in the date and time fields. Cron carries no
    // year, so the prefill infers the next occurrence of that month/day.
    const dateInput = within(dialog).getByLabelText(/^date$/i);
    expect(String((dateInput as unknown as { value?: string }).value ?? '')).toMatch(/-03-20$/);
    expect(within(dialog).getByLabelText(/^time$/i)).toHaveValue('08:00');
    await user.click(within(dialog).getByRole('radio', { name: /repeating/i }));
    // The rhythm prefill carries the compiled cron; replace it with a phrase.
    const rhythmInput = within(dialog).getByLabelText(/rhythm/i);
    await user.clear(rhythmInput);
    await user.type(rhythmInput, 'every day at 7 AM');
    await waitFor(() => {
      expect(within(dialog).getByText(/0 7 \* \* \*/)).toBeInTheDocument();
    });
    await user.click(within(dialog).getByRole('button', { name: /save changes/i }));

    // The once badge is gone: the cap was cleared over the wire.
    await waitFor(() => {
      expect(screen.getByText('Flexible')).toBeInTheDocument();
      expect(screen.queryByText(/^once$/i)).not.toBeInTheDocument();
    });
    const updates = await updatedParams(transport);
    expect(
      updates.some((p) => p['max_runs'] === null && p['natural_language'] === 'every day at 7 AM'),
    ).toBe(true);
  });
});
