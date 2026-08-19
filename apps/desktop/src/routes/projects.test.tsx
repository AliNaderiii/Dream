/**
 * Projects route (S06) — exercises the real echo transport end to end:
 * create, group a session, ungroup, and delete-with-confirm.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient } from '@/lib/bridge/client';
import { ProjectsRoute } from '@/routes/projects';

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={['/projects']}>
      <ProjectsRoute />
    </MemoryRouter>,
  );
}

describe('ProjectsRoute (S06)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('creates a project with a workspace folder', async () => {
    const user = userEvent.setup();
    renderRoute();

    // The placeholder shell is gone: this is the working screen.
    expect(screen.getByRole('heading', { level: 2, name: 'Projects' })).toBeInTheDocument();
    expect(screen.queryByText(/Built in P-03/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New project' }));
    await user.type(await screen.findByLabelText('Name'), 'Thesis');
    await user.type(screen.getByLabelText(/Workspace folder/), '/work/thesis');
    await user.click(screen.getByRole('button', { name: 'Create project' }));

    expect(await screen.findByRole('heading', { level: 3, name: 'Thesis' })).toBeInTheDocument();
    expect(screen.getByText('/work/thesis')).toBeInTheDocument();
  });

  it('groups a session under a project and ungroups it again', async () => {
    const user = userEvent.setup();
    const client = getBridgeClient();
    await client.call('session.create', { title: 'Field notes' });
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New project' }));
    await user.type(await screen.findByLabelText('Name'), 'Research');
    await user.click(screen.getByRole('button', { name: 'Create project' }));
    await screen.findByRole('heading', { level: 3, name: 'Research' });

    // The ungrouped session is offered and lands inside the project.
    const addSelect = screen.getByRole('combobox', { name: 'Add session: Research' });
    await user.selectOptions(addSelect, 'Field notes');
    expect(await screen.findByText('Field notes')).toBeInTheDocument();

    // Removing it from the project keeps the session alive but ungrouped.
    await user.click(screen.getByRole('button', { name: 'Remove from project: Field notes' }));
    await screen.findByText('No sessions in this project yet.');
    expect(screen.queryByRole('button', { name: 'Field notes' })).toBeNull();
    const sessions = await client.call<{ sessions: Array<{ id: string }> }>('session.list', {});
    expect(sessions.sessions).toHaveLength(1);
  });

  it('deletes a project only after confirmation', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New project' }));
    await user.type(await screen.findByLabelText('Name'), 'Spring cleaning');
    await user.click(screen.getByRole('button', { name: 'Create project' }));
    await screen.findByRole('heading', { level: 3, name: 'Spring cleaning' });

    await user.click(screen.getByRole('button', { name: 'Delete project: Spring cleaning' }));

    // The confirm dialog explains that sessions survive.
    expect(screen.getByText('Delete this project?')).toBeInTheDocument();
    expect(screen.getByText(/sessions are kept/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete project' }));
    await waitFor(() => {
      expect(screen.queryByRole('heading', { level: 3, name: 'Spring cleaning' })).toBeNull();
    });
  });

  it('rejects an unnamed project', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('button', { name: 'New project' }));
    const create = await screen.findByRole('button', { name: 'Create project' });
    expect(create).toBeDisabled();
  });
});
