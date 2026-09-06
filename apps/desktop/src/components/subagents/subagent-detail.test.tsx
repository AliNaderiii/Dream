/**
 * P-15: the detail pane's explicit stream state, truncation notice, and
 * control accessibility — rendered pure, no bridge.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SubagentDetail } from '@/components/subagents/subagent-detail';
import type { BridgeSubagent } from '@/lib/bridge/types';

function agentFixture(overrides: Partial<BridgeSubagent> = {}): BridgeSubagent {
  return {
    subagent_id: 'sub_test01',
    id: 'sub_test01',
    name: 'Worker',
    parent_session_id: null,
    model_provider: 'echo',
    model_name: 'echo',
    system_prompt: '',
    tools: ['calculate'],
    prompt: 'Do the thing',
    context: '',
    status: 'running',
    created_at: 1_700_000_000,
    started_at: 1_700_000_000,
    finished_at: null,
    max_turns: 8,
    max_tokens: 20_000,
    max_duration: 120,
    turn_count: 1,
    token_count: 100,
    result: null,
    error: null,
    pipeline_id: null,
    pipeline_index: null,
    limit_hit: null,
    log_dropped: 0,
    elapsed: 2,
    progress: 0.1,
    ...overrides,
  };
}

const noop = () => {};

describe('SubagentDetail (P-15)', () => {
  it('renders each stream phase with a stable status role', () => {
    const { rerender } = render(
      <SubagentDetail
        agent={agentFixture()}
        log={[]}
        streamPhase="connecting"
        onCancel={noop}
        onPause={noop}
        onResume={noop}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Connecting to the log stream…');

    for (const [phase, text] of [
      ['live', 'Live'],
      ['ended', 'Stream ended'],
      ['disconnected', 'Stream disconnected — showing the last known log.'],
    ] as const) {
      rerender(
        <SubagentDetail
          agent={agentFixture()}
          log={[]}
          streamPhase={phase}
          onCancel={noop}
          onPause={noop}
          onResume={noop}
        />,
      );
      expect(screen.getByRole('status')).toHaveTextContent(text);
    }
  });

  it('states how many earlier log lines were dropped', () => {
    render(
      <SubagentDetail
        agent={agentFixture({ log_dropped: 0 })}
        log={[{ ts: 1_700_000_001, level: 'info', message: 'tail line', seq: 42 }]}
        logDropped={37}
        streamPhase="live"
        onCancel={noop}
        onPause={noop}
        onResume={noop}
      />,
    );
    expect(
      screen.getByText('37 earlier lines dropped to keep the log bounded.'),
    ).toBeInTheDocument();
    expect(screen.getByText('tail line')).toBeInTheDocument();
  });

  it('omits the truncation notice when nothing was dropped', () => {
    render(
      <SubagentDetail
        agent={agentFixture()}
        log={[]}
        logDropped={0}
        onCancel={noop}
        onPause={noop}
        onResume={noop}
      />,
    );
    expect(screen.queryByText(/earlier lines dropped/)).not.toBeInTheDocument();
  });

  it('keeps stable accessible names on the controls in both states', () => {
    const onPause = vi.fn();
    const onResume = vi.fn();
    const { rerender } = render(
      <SubagentDetail
        agent={agentFixture({ status: 'running' })}
        log={[]}
        onCancel={noop}
        onPause={onPause}
        onResume={onResume}
      />,
    );
    expect(screen.getByRole('button', { name: 'Pause' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();

    rerender(
      <SubagentDetail
        agent={agentFixture({ status: 'paused' })}
        log={[]}
        onCancel={noop}
        onPause={onPause}
        onResume={onResume}
      />,
    );
    expect(screen.getByRole('button', { name: 'Resume' })).toBeEnabled();

    rerender(
      <SubagentDetail
        agent={agentFixture({ status: 'completed', finished_at: 1_700_000_010, result: 'done' })}
        log={[]}
        onCancel={noop}
        onPause={onPause}
        onResume={onResume}
      />,
    );
    expect(screen.getByRole('button', { name: 'Pause' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });

  it('renders the terminal error state with an alert', () => {
    render(
      <SubagentDetail
        agent={agentFixture({ status: 'failed', error: 'RuntimeError: [REDACTED:openai-key]' })}
        log={[]}
        onCancel={noop}
        onPause={noop}
        onResume={noop}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('RuntimeError: [REDACTED:openai-key]');
  });
});
