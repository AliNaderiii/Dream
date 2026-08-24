/**
 * Skills learning workspace (MEM Stage F) — the pinned laws.
 *
 * Statistics count every non-ok outcome, the diff never mangles a line, the
 * echo classifier refuses like the kernel (bilingually, up front), and the
 * panel writes nothing without an explicit click.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { act } from 'react';
import i18n from 'i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SkillsV2 } from '@/components/skills/skills-v2';
import {
  diffLines,
  median,
  summariseUses,
  type SkillUseRow,
} from '@/components/skills/skills-v2-model';
import { EchoSkills2Runtime } from '@/lib/bridge/echo-skills2';
import { getBridgeClient, resetBridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
  document.documentElement.dir = 'ltr';
});

/** A transport answering only the skills.* v2 family, with test knobs. */
class Skills2Transport implements BridgeTransport {
  readonly kind = 'echo' as const;
  readonly runtime = new EchoSkills2Runtime();
  calls: string[] = [];
  hangReads = false;
  failLedgerOnce = false;
  emptyUses = false;
  largeUses = false;
  private stateHandler: ((state: BridgeConnectionState) => void) | undefined;

  request<T>(
    _id: RpcId,
    method: string,
    params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    this.calls.push(method);
    if (!method.startsWith('skills.')) {
      return Promise.reject(new Error(`unexpected method ${method}`));
    }
    if (this.hangReads && method === 'skills.use_log') {
      return new Promise<T>(() => {});
    }
    if (this.failLedgerOnce && method === 'skills.use_log') {
      this.failLedgerOnce = false;
      return Promise.reject(new Error('skill ledger unavailable'));
    }
    if (this.emptyUses && method === 'skills.use_log') {
      return Promise.resolve({ uses: [] } as T);
    }
    if (this.largeUses && method === 'skills.use_log') {
      const uses: SkillUseRow[] = Array.from({ length: 1000 }, (_, index) => ({
        name: `fixture-skill-${index}`,
        invoked_at: 1_780_000_000 + index,
        outcome: index % 5 === 0 ? 'error' : 'ok',
        duration_ms: index % 50,
        source: 'slash',
      }));
      return Promise.resolve({ uses } as T);
    }
    return Promise.resolve(this.runtime.handle(method, params) as T);
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandler = handler;
    return () => {
      this.stateHandler = undefined;
    };
  }

  pushState(state: BridgeConnectionState): void {
    this.stateHandler?.(state);
  }

  reconnect() {}
}

function mountPanel(options: Partial<InstanceType<typeof Skills2Transport>> = {}) {
  const transport = Object.assign(new Skills2Transport(), options);
  resetBridgeClient();
  const client = getBridgeClient();
  client.setTransport(transport);
  return { transport, client, ...render(<SkillsV2 />) };
}

const NOTES_ROW: SkillUseRow = {
  name: 'notes',
  invoked_at: 1,
  outcome: 'ok',
  duration_ms: 10,
  source: 'slash',
};

describe('use-log statistics', () => {
  it('takes the median of an even and an odd sample', () => {
    expect(median([10, 30, 20, 40])).toBe(25);
    expect(median([30, 10, 20])).toBe(20);
    expect(median([])).toBe(0);
  });

  it('counts any outcome that is not exactly ok as a failure', () => {
    const stats = summariseUses([
      NOTES_ROW,
      { ...NOTES_ROW, outcome: 'error' },
      { ...NOTES_ROW, outcome: 'timeout' },
      { ...NOTES_ROW, outcome: 'Cancelled' },
    ]);
    expect(stats[0]).toMatchObject({ name: 'notes', runs: 4, failures: 3 });
  });

  it('orders skills busiest first, breaking ties by name', () => {
    const stats = summariseUses([
      { ...NOTES_ROW, name: 'zeta' },
      { ...NOTES_ROW, name: 'alpha' },
      { ...NOTES_ROW, name: 'alpha' },
      { ...NOTES_ROW, name: 'mid' },
      { ...NOTES_ROW, name: 'alpha' },
      { ...NOTES_ROW, name: 'mid' },
    ]);
    expect(stats.map((stat) => stat.name)).toEqual(['alpha', 'mid', 'zeta']);
    expect(stats[0].runs).toBe(3);
  });
});

describe('review diff', () => {
  it('reports an unchanged body as entirely unchanged', () => {
    const body = '## Purpose\n\nSame skill.\n';
    const lines = diffLines(body, body);
    expect(lines.every((line) => line.kind === 'same')).toBe(true);
    expect(lines.map((line) => line.text).join('\n')).toBe(body);
  });

  it('marks an inserted line as added and keeps the rest stable', () => {
    const lines = diffLines('## Purpose\n\nBody.\n', '## Purpose\n\nInserted.\n\nBody.\n');
    const added = lines.find((line) => line.kind === 'added');
    expect(added?.text).toBe('Inserted.');
    expect(lines.filter((line) => line.kind === 'same').map((line) => line.text)).toEqual(
      expect.arrayContaining(['## Purpose', 'Body.', '']),
    );
  });

  it('marks a deleted line as removed', () => {
    const lines = diffLines('keep\ndrop\n', 'keep\n');
    expect(lines.find((line) => line.kind === 'removed')?.text).toBe('drop');
  });

  it('handles an empty side without losing content', () => {
    const fromEmpty = diffLines('', 'a\nb');
    expect(fromEmpty.map((line) => line.kind)).toEqual(['added', 'added']);
    const toEmpty = diffLines('a\nb', '');
    expect(toEmpty.map((line) => line.kind)).toEqual(['removed', 'removed']);
  });

  it('diffs Persian bodies without mangling the lines', () => {
    const before = '## هدف\n\nمهارت گزارش هفتگی';
    const after = '## هدف\n\nمهارت گزارش هفتگی و ماهانه';
    const lines = diffLines(before, after);
    expect(lines.some((line) => line.kind === 'same' && line.text === '## هدف')).toBe(true);
    expect(lines.find((line) => line.kind === 'removed')?.text).toBe('مهارت گزارش هفتگی');
    expect(lines.find((line) => line.kind === 'added')?.text).toBe('مهارت گزارش هفتگی و ماهانه');
  });
});

describe('echo skills v2 runtime', () => {
  it('refuses a URL source while the network is off, in both languages', () => {
    const runtime = new EchoSkills2Runtime();
    expect(() =>
      runtime.handle('skills.learn_classify', { argument: 'https://example.com/x' }),
    ).toThrow(/network tools/i);
    try {
      runtime.handle('skills.learn_classify', { argument: 'https://example.com/x' });
      expect.unreachable('classify must refuse');
    } catch (err) {
      expect((err as Error).message).toContain('\u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc');
    }
  });

  it('accepts the same URL once the network is enabled', () => {
    const runtime = new EchoSkills2Runtime();
    runtime.setNetworkEnabled(true);
    const out = runtime.handle('skills.learn_classify', {
      argument: 'https://example.com/x',
    }) as { source: { kind: string } };
    expect(out.source.kind).toBe('url');
  });

  it('refuses an empty conversation rather than inventing a source', () => {
    const runtime = new EchoSkills2Runtime();
    expect(() =>
      runtime.handle('skills.learn_classify', { argument: 'conversation', history: [] }),
    ).toThrow(/could not be read/i);
  });

  it('classifies notes, paths and folders', () => {
    const runtime = new EchoSkills2Runtime();
    const kinds = (
      runtime.handle('skills.learn_classify', { argument: 'dream deployment notes' }) as {
        source: { kind: string };
      }
    ).source.kind;
    expect(kinds).toBe('notes');
    expect(
      (
        runtime.handle('skills.learn_classify', { argument: 'docs/runbook.md' }) as {
          source: { kind: string };
        }
      ).source.kind,
    ).toBe('path');
    expect(
      (
        runtime.handle('skills.learn_classify', { argument: 'docs/' }) as {
          source: { kind: string };
        }
      ).source.kind,
    ).toBe('corpus');
  });

  it('rejects malformed parameters at the boundary', () => {
    const runtime = new EchoSkills2Runtime();
    expect(() => runtime.handle('skills.learn_classify', { argument: 42 })).toThrow(
      /argument must be a string/i,
    );
    expect(() =>
      runtime.handle('skills.learn_classify', { argument: 'x', history: 'chat' }),
    ).toThrow(/history must be a list/i);
    expect(() => runtime.handle('skills.versions', {})).toThrow(/name must be a non-empty string/i);
  });
});

describe('SkillsV2 panel', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('shows a loading status until the ledger answers', () => {
    mountPanel({ hangReads: true });
    expect(
      screen.getByRole('status', { name: /loading the learning workspace/i }),
    ).toBeInTheDocument();
  });

  it('cancels the in-flight load on unmount', async () => {
    const transport = new Skills2Transport();
    transport.hangReads = true;
    resetBridgeClient();
    const client = getBridgeClient();
    client.setTransport(transport);
    const callSpy = vi.spyOn(client, 'call');
    const { unmount } = render(<SkillsV2 />);
    await act(async () => {});
    unmount();
    const read = callSpy.mock.calls.find(([method]) => method === 'skills.use_log');
    expect(read).toBeDefined();
    expect(read?.[2]?.signal?.aborted).toBe(true);
  });

  it('renders per-skill run counts and failures', async () => {
    mountPanel();
    const row = await screen.findByText('weekly-report');
    const container = (row.closest('[role="listitem"]') ?? row.parentElement) as HTMLElement;
    expect(within(container).getByText(/3 runs/i)).toBeInTheDocument();
    expect(within(container).getByText(/1 failures/i)).toBeInTheDocument();
    expect(screen.getByText('triage-inbox')).toBeInTheDocument();
  });

  it('renders the use-stats empty state', async () => {
    mountPanel({ emptyUses: true });
    expect(await screen.findByText('No skill runs recorded yet')).toBeInTheDocument();
  });

  it('keeps a 1,000-skill use log below the mounted-row bound', async () => {
    const { container } = mountPanel({ largeUses: true });
    await screen.findAllByRole('listitem');
    const mounted = container.querySelectorAll('[role="listitem"]').length;
    console.info(`skills_v2_fixture_rows=1000 mounted_rows=${mounted}`);
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(60);
  });

  it('surfaces a ledger failure with a retry that recovers', async () => {
    mountPanel({ failLedgerOnce: true });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/skill ledger unavailable/i);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('weekly-report')).toBeInTheDocument();
  });

  it('writes a proposal only on an explicit approve', async () => {
    const { client } = mountPanel();
    const callSpy = vi.spyOn(client, 'call');
    await screen.findByText('weekly-report');
    expect(
      await screen.findByRole('button', { name: 'Approve weekly-report' }),
    ).toBeInTheDocument();
    expect(callSpy.mock.calls.some(([method]) => method === 'skills.apply_proposal')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Approve weekly-report' }));
    await waitFor(() =>
      expect(callSpy.mock.calls.some(([method]) => method === 'skills.apply_proposal')).toBe(true),
    );
    expect(await screen.findByText(/Approved weekly-report/i)).toBeInTheDocument();
  });

  it('discards a proposal without writing anything', async () => {
    const { client } = mountPanel();
    const callSpy = vi.spyOn(client, 'call');
    await screen.findByText('weekly-report');
    fireEvent.click(screen.getByRole('button', { name: 'Discard weekly-report' }));
    await waitFor(() =>
      expect(callSpy.mock.calls.some(([method]) => method === 'skills.discard_proposal')).toBe(
        true,
      ),
    );
    expect(callSpy.mock.calls.some(([method]) => method === 'skills.apply_proposal')).toBe(false);
    expect(await screen.findByText(/Discarded weekly-report/i)).toBeInTheDocument();
  });

  it('disables the inbox and /learn while the bridge is offline', async () => {
    const transport = new Skills2Transport();
    resetBridgeClient();
    getBridgeClient().setTransport(transport);
    queueMicrotask(() => transport.pushState('disconnected'));
    render(<SkillsV2 />);

    expect(await screen.findByRole('button', { name: 'Approve weekly-report' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard weekly-report' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /learn a skill/i })).toBeDisabled();
  });

  it('warns in the dialog before a URL is submitted while offline', async () => {
    mountPanel();
    await screen.findByText('weekly-report');
    fireEvent.click(screen.getByRole('button', { name: /learn a skill/i }));
    expect(
      await screen.findByText(/network tools are off — a url source will be refused/i),
    ).toBeInTheDocument();
  });

  it('renders the kernel refusal for an offline URL source', async () => {
    mountPanel();
    await screen.findByText('weekly-report');
    fireEvent.click(screen.getByRole('button', { name: /learn a skill/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Source'), {
      target: { value: 'https://example.com/runbook' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Classify' }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toContain('\u0627\u06cc\u0646\u062a\u0631\u0646\u062a\u06cc');
    expect(alert.textContent).toContain('network tools');
  });

  it('resolves pasted notes to a skill name before committing', async () => {
    const { client } = mountPanel();
    const callSpy = vi.spyOn(client, 'call');
    await screen.findByText('weekly-report');
    fireEvent.click(screen.getByRole('button', { name: /learn a skill/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Source'), {
      target: { value: 'dream deployment runbook notes' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Classify' }));
    expect(
      await within(dialog).findByText(/resolves to skill: dream-deployment-runbook/i),
    ).toBeInTheDocument();
    expect(callSpy.mock.calls.some(([method]) => method === 'skills.save')).toBe(false);

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Allow once' }));
    await waitFor(() =>
      expect(callSpy.mock.calls.some(([method]) => method === 'skills.save')).toBe(true),
    );
  });

  it('shows the version diff and the references tree for a selected skill', async () => {
    mountPanel();
    fireEvent.click(await screen.findByText('weekly-report'));
    expect(await screen.findByText(/compare versions/i)).toBeInTheDocument();
    expect(await screen.findByText(/\+3 added/i)).toBeInTheDocument();
    expect(screen.getByText(/references\/glossary\.md/)).toBeInTheDocument();
    expect(screen.getByText(/references\/seven-day-window\.md/)).toBeInTheDocument();
  });

  it('says so when a skill has only one saved version', async () => {
    mountPanel();
    fireEvent.click(await screen.findByText('triage-inbox'));
    expect(
      await screen.findByText(/only one saved version — nothing to compare yet/i),
    ).toBeInTheDocument();
  });
});

describe('SkillsV2 in Persian', () => {
  it('renders the workspace in Persian with no English fallback', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountPanel();
    expect(await screen.findByRole('region', { name: 'کارگاه یادگیری' })).toBeInTheDocument();
    await screen.findByText('weekly-report');
    expect(screen.getByText('آمار اجرا')).toBeInTheDocument();
    expect(screen.getByText('صندوق تأیید')).toBeInTheDocument();
    expect(screen.queryByText('Run statistics')).toBeNull();
    expect(screen.queryByText('Approval inbox')).toBeNull();
  });
});
