import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { SkillsRoute } from '@/routes/skills';

describe('SkillsRoute', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('lists the installed skills with their enabled state', async () => {
    render(<SkillsRoute />);
    await screen.findByText('weekly report');

    expect(screen.getByRole('switch', { name: /Disable weekly report/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('switch', { name: /Enable triage inbox/ })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('flips the enable toggle optimistically', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);
    await screen.findByText('weekly report');

    await user.click(screen.getByRole('switch', { name: /Disable weekly report/ }));

    expect(screen.getByRole('switch', { name: /Enable weekly report/ })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('shows the skill file when a skill is selected', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);

    await user.click(await screen.findByText('weekly report'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    });
    expect(screen.getByText(/Collect sessions from the past 7 days/)).toBeInTheDocument();
  });

  it('rejects an invalid paste in the import dialog', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);
    await screen.findByText('weekly report');

    await user.click(screen.getByRole('button', { name: /Import/ }));
    const dialog = await screen.findByRole('dialog');

    await user.type(
      within(dialog).getByLabelText(/Or paste the skill/),
      'name: bad{Enter}description: nope{Enter}steps:{Enter}- read /etc/passwd',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Validate' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent(/absolute file paths/);
  });

  it('previews and installs a valid pasted skill', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);
    await screen.findByText('weekly report');

    await user.click(screen.getByRole('button', { name: /Import/ }));
    const dialog = await screen.findByRole('dialog');

    await user.type(
      within(dialog).getByLabelText(/Or paste the skill/),
      'name: brand new{Enter}description: A fresh skill.{Enter}steps:{Enter}- step one',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Validate' }));

    expect(await within(dialog).findByText('Steps')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /Install/ }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(screen.getByText('brand new')).toBeInTheDocument();
  });

  it('offers overwrite or rename when the name already exists', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);
    await screen.findByText('weekly report');

    await user.click(screen.getByRole('button', { name: /Import/ }));
    const dialog = await screen.findByRole('dialog');

    await user.type(
      within(dialog).getByLabelText(/Or paste the skill/),
      'name: weekly report{Enter}description: Replacement.{Enter}steps:{Enter}- new step',
    );
    await user.click(within(dialog).getByRole('button', { name: 'Validate' }));
    await user.click(within(dialog).getByRole('button', { name: /Install/ }));

    expect(await within(dialog).findByText(/already exists/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Overwrite' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /Install as new name/ })).toBeInTheDocument();
  });

  it('confirms before deleting a skill', async () => {
    const user = userEvent.setup();
    render(<SkillsRoute />);

    await user.click(await screen.findByText('triage inbox'));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Delete/ })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /Delete/ }));

    expect(await screen.findByText(/Delete triage inbox\?/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(screen.queryByText('triage inbox')).not.toBeInTheDocument();
    });
  });
});
