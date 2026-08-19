import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { SubagentsRoute } from '@/routes/subagents';

/** Spawns one child through the dialog and waits for it to appear in the list. */
async function spawnOne(user: ReturnType<typeof userEvent.setup>, task: string, name: string) {
  await user.click(screen.getByRole('button', { name: /New subagent/ }));
  const dialog = await screen.findByRole('dialog');

  await user.type(within(dialog).getByRole('textbox', { name: 'Name' }), name);
  await user.type(within(dialog).getByRole('textbox', { name: 'Task' }), task);
  await user.click(within(dialog).getByRole('button', { name: 'Spawn' }));

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  // The name shows up twice (list row and detail heading); the row is enough.
  return within(screen.getByRole('list', { name: 'Subagents' })).findByText(name);
}

describe('SubagentsRoute', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('starts empty and offers a way in', async () => {
    render(<SubagentsRoute />);

    expect(await screen.findByText('No subagents yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Spawn a subagent/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Council review/ })).toBeInTheDocument();
  });

  it('runs a council: three columns appear and a winner is crowned', async () => {
    const user = userEvent.setup();
    render(<SubagentsRoute />);
    await screen.findByText('No subagents yet');

    await user.click(screen.getByRole('button', { name: /Council review/ }));
    const dialog = await screen.findByRole('dialog');
    await user.type(
      within(dialog).getByRole('textbox', { name: 'Topic' }),
      'Should we ship monthly releases?',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Run council' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // The proposer is selected automatically, and the widget shows one column
    // per role while the echo members run in order.
    expect(await screen.findByRole('region', { name: 'Proposer' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Critic' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Judge' })).toBeInTheDocument();

    // The winner strip appears once the echo judge completes.
    await waitFor(
      () => {
        expect(screen.getByText('Winner')).toBeInTheDocument();
      },
      { timeout: 8000 },
    );
  });

  it('spawns a child, selects it, and runs it to completion', async () => {
    const user = userEvent.setup();
    render(<SubagentsRoute />);
    await screen.findByText('No subagents yet');

    await spawnOne(user, 'Summarise the notes', 'Researcher');

    // The newest child is selected automatically, so its detail is on screen.
    expect(await screen.findByRole('region', { name: 'Subagent Researcher' })).toBeInTheDocument();

    // The echo runtime finishes on its own; the result then shows up.
    await waitFor(
      () => {
        expect(screen.getByText(/Echo: Summarise the notes/)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  });

  it('streams the log for the selected child', async () => {
    const user = userEvent.setup();
    render(<SubagentsRoute />);
    await screen.findByText('No subagents yet');

    await spawnOne(user, 'Draft the summary', 'Writer');

    // Log lines arrive over `subagent.logs`, which replays from the start.
    await waitFor(
      () => {
        expect(screen.getByText(/spawned/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
  });

  it('switches the detail pane when another child is picked', async () => {
    const user = userEvent.setup();
    render(<SubagentsRoute />);
    await screen.findByText('No subagents yet');

    await spawnOne(user, 'First task', 'Alpha');
    await spawnOne(user, 'Second task', 'Beta');

    const list = screen.getByRole('list', { name: 'Subagents' });
    await user.click(within(list).getByText('Alpha'));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'Subagent Alpha' })).toBeInTheDocument();
    });
  });

  it('keeps a selection when the list refreshes', async () => {
    const user = userEvent.setup();
    render(<SubagentsRoute />);
    await screen.findByText('No subagents yet');

    await spawnOne(user, 'Long running task', 'Keeper');
    await screen.findByRole('region', { name: 'Subagent Keeper' });

    // Polling replaces the list objects; the selection must survive it.
    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'Subagent Keeper' })).toBeInTheDocument();
    });
  });
});
