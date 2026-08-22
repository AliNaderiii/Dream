import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SubagentLogTail } from '@/components/subagents/subagent-log-tail';
import type { BridgeLogEntry } from '@/lib/bridge/types';

describe('SubagentLogTail', () => {
  it('tail-follows 1,000 streamed rows while keeping the DOM bounded', () => {
    const log: BridgeLogEntry[] = Array.from({ length: 1000 }, (_, index) => ({
      ts: 1_700_000_000 + index,
      level: 'info',
      message: `log-${index}`,
    }));
    const { container } = render(<SubagentLogTail log={log} />);
    const viewport = container.querySelector<HTMLElement>('[data-virtualized="true"]');
    if (!viewport) throw new Error('missing virtual log viewport');

    expect(screen.getAllByRole('listitem').length).toBeLessThan(60);
    console.info(`subagent_log_rows=1000 mounted_rows=${screen.getAllByRole('listitem').length}`);
    expect(screen.getByText('log-999')).toBeInTheDocument();
    fireEvent.scroll(viewport, { target: { scrollTop: 0 } });
    expect(screen.getByText('log-0')).toBeInTheDocument();
    expect(screen.queryByText('log-999')).not.toBeInTheDocument();
  });
});
