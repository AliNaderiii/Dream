import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';
import { SkillsRoute } from '@/routes/skills';

class SkillsStateTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private readonly echo = new EchoBridgeTransport();
  listCalls = 0;
  failListOnce = false;
  hangList = false;
  empty = false;
  large = false;

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    if (method === 'skill.list') {
      this.listCalls += 1;
      if (this.hangList) return new Promise<T>(() => {});
      if (this.failListOnce) {
        this.failListOnce = false;
        return Promise.reject(new Error('skill registry unavailable'));
      }
      if (this.empty) return Promise.resolve({ skills: [], problems: [] } as T);
      if (this.large) {
        const skills = Array.from({ length: 1000 }, (_, index) => ({
          name: `fixture-skill-${index}`,
          description: `Fixture skill ${index}`,
          steps: [],
          filename: `fixture-${index}.md`,
          enabled: true,
        }));
        return Promise.resolve({ skills, problems: [] } as T);
      }
    }
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(_handler: (state: BridgeConnectionState) => void) {
    return () => {};
  }

  reconnect() {}
}

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

  it('renders a five-card loading skeleton and cancels it on unmount', () => {
    const transport = new SkillsStateTransport();
    transport.hangList = true;
    getBridgeClient().setTransport(transport);
    const { container, unmount } = render(<SkillsRoute />);
    expect(screen.getByRole('status', { name: 'Loading skills…' })).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(5);
    unmount();
    expect(screen.queryByRole('status', { name: 'Loading skills…' })).not.toBeInTheDocument();
  });

  it('keeps a 1,000-skill fixture below the mounted-row bound', async () => {
    const transport = new SkillsStateTransport();
    transport.large = true;
    getBridgeClient().setTransport(transport);
    render(<SkillsRoute />);

    await screen.findByText('fixture-skill-0');
    const mountedRows = screen.getAllByRole('listitem').length;
    expect(mountedRows).toBeLessThan(60);
    console.info(`skills_fixture_rows=1000 mounted_rows=${mountedRows}`);
  });

  it('renders the installed-skills empty state', async () => {
    const transport = new SkillsStateTransport();
    transport.empty = true;
    getBridgeClient().setTransport(transport);
    render(<SkillsRoute />);
    expect(await screen.findByText('No skills installed')).toBeInTheDocument();
  });

  it('retries a failed bridge request', async () => {
    const user = userEvent.setup();
    const transport = new SkillsStateTransport();
    transport.failListOnce = true;
    getBridgeClient().setTransport(transport);
    render(<SkillsRoute />);
    expect(await screen.findByRole('alert')).toHaveTextContent('skill registry unavailable');
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('weekly report')).toBeInTheDocument();
    expect(transport.listCalls).toBe(2);
  });
});
