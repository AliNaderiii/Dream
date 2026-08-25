import { beforeEach, describe, expect, it, vi } from 'vitest';

const bridge = vi.hoisted(() => ({
  call: vi.fn(),
}));

vi.mock('@/lib/bridge/client', () => ({
  getBridgeClient: () => ({ transportKind: 'tauri', call: bridge.call }),
}));

import {
  createDataQaSession,
  deleteDataQaSession,
  discoverDataQa,
  getDataQaSession,
  listDataQaSessions,
} from '@/lib/bridge/dataqa';

describe('Data Q&A bridge wire methods', () => {
  beforeEach(() => {
    bridge.call.mockReset();
    bridge.call.mockResolvedValue({});
  });

  it('preserves fixed nested session method names on the real transport', async () => {
    await createDataQaSession('data/sales.csv', 'sales', 'dataset-1');
    await listDataQaSessions();
    await getDataQaSession('a'.repeat(32));
    await deleteDataQaSession('b'.repeat(32));

    expect(bridge.call.mock.calls).toEqual([
      [
        'dataqa.sessions.create',
        { source: 'data/sales.csv', query: 'sales', dataset_id: 'dataset-1' },
      ],
      ['dataqa.sessions.list', {}],
      ['dataqa.sessions.get', { session_id: 'a'.repeat(32) }],
      ['dataqa.sessions.delete', { session_id: 'b'.repeat(32) }],
    ]);
  });

  it('uses the extension client for single-segment Data Q&A methods', async () => {
    await discoverDataQa('revenue', 'data');
    expect(bridge.call).toHaveBeenCalledWith(
      'dataqa.discover',
      { query: 'revenue', source: 'data' },
      {},
    );
  });
});
