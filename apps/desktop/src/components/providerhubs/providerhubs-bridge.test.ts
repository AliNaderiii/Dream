import { beforeEach, describe, expect, it, vi } from 'vitest';

const bridge = vi.hoisted(
  (): { call: ReturnType<typeof vi.fn>; transportKind: 'tauri' | 'echo' } => ({
    call: vi.fn(),
    transportKind: 'tauri',
  }),
);

vi.mock('@/lib/bridge/client', () => ({
  getBridgeClient: () => ({ transportKind: bridge.transportKind, call: bridge.call }),
}));

import {
  diagnoseRuntime,
  filterCatalog,
  getGateway,
  listCatalog,
  listRuntimes,
  mapProviderHubsError,
  resolveRoute,
  ROUTE_PRIORITY,
  testRuntime,
  updateGateway,
} from '@/lib/bridge/providerhubs';
import { resetEchoProviderHubs } from '@/lib/bridge/echo-providerhubs';

describe('providerhubs route priority', () => {
  it('keeps hosted → aval → ollama → byok → echo', () => {
    expect([...ROUTE_PRIORITY]).toEqual(['hosted', 'aval', 'ollama', 'byok', 'echo']);
  });
});

describe('providerhubs catalog filter', () => {
  it('matches name, id, and runtime without inventing entries', () => {
    const entries = [
      {
        id: 'ollama',
        name: 'Ollama',
        local: true,
        runtimes: ['ollama' as const],
        cost_tier: 'local' as const,
        data_leaves_machine: false,
        privacy_en: 'Data stays on this machine.',
        privacy_fa: 'داده روی همین دستگاه می‌ماند.',
        tool_calling: true,
        notes: 'Recommended local default.',
      },
      {
        id: 'hosted',
        name: 'Hosted',
        local: false,
        runtimes: [],
        cost_tier: 'optional' as const,
        data_leaves_machine: true,
        privacy_en: 'Requests leave this machine when this route is used.',
        privacy_fa: 'در صورت استفاده از این مسیر، درخواست‌ها این دستگاه را ترک می‌کنند.',
        tool_calling: true,
        notes: 'Optional hosted route.',
      },
    ];
    expect(filterCatalog(entries, 'olla')).toHaveLength(1);
    expect(filterCatalog(entries, 'hosted')[0]?.id).toBe('hosted');
    expect(filterCatalog(entries, 'missing')).toHaveLength(0);
  });
});

describe('providerhubs bridge wire methods', () => {
  beforeEach(() => {
    bridge.call.mockReset();
    bridge.call.mockResolvedValue({});
    bridge.transportKind = 'tauri';
  });

  it('sends single-segment providerhubs methods on the real transport', async () => {
    await listCatalog('ollama');
    await listRuntimes();
    await testRuntime('vllm');
    await diagnoseRuntime('sglang');
    await resolveRoute();
    await getGateway();
    await updateGateway({ enabled: true, tool_id: 'web_search', tool_enabled: true });

    expect(bridge.call.mock.calls).toEqual([
      ['providerhubs.catalog', { query: 'ollama' }, {}],
      ['providerhubs.runtimes', {}, {}],
      ['providerhubs.test', { runtime_id: 'vllm' }, {}],
      ['providerhubs.diagnose', { runtime_id: 'sglang' }, {}],
      ['providerhubs.route', {}, {}],
      ['providerhubs.gateway', {}, {}],
      [
        'providerhubs.gateway_update',
        { enabled: true, tool_id: 'web_search', tool_enabled: true },
        {},
      ],
    ]);
  });

  it('rejects unknown runtime ids before any wire call', async () => {
    await expect(testRuntime('not-a-runtime')).rejects.toThrow('unknown runtime');
    expect(bridge.call).not.toHaveBeenCalled();
  });
});

describe('providerhubs echo runtime', () => {
  beforeEach(() => {
    bridge.transportKind = 'echo';
    resetEchoProviderHubs();
  });

  it('lists six local runtimes and never leaks credentials', async () => {
    const { runtimes, recommended } = await listRuntimes();
    expect(recommended).toBe('ollama');
    expect(runtimes.map((item) => item.id)).toEqual([
      'ollama',
      'vllm',
      'sglang',
      'llamacpp',
      'lmstudio',
      'generic',
    ]);
    const blob = JSON.stringify(runtimes);
    expect(blob).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
    expect(blob).not.toMatch(/ghp_[A-Za-z0-9]{8,}/);
    expect(blob).not.toMatch(/AKIA[A-Z0-9]{8,}/);
    expect(runtimes.every((item) => item.cost_tier !== undefined)).toBe(true);
    expect(JSON.stringify(runtimes)).not.toMatch(/\$\d/);
  });

  it('flags the generic fallback parser as reduced reliability', async () => {
    const diagnosis = await diagnoseRuntime('generic');
    expect(diagnosis.reduced_reliability).toBe(true);
    expect(diagnosis.firing).toBe(true);
  });

  it('gives an actionable vLLM fix and keeps the gateway optional', async () => {
    const diagnosis = await diagnoseRuntime('vllm');
    expect(diagnosis.firing).toBe(false);
    expect(diagnosis.fix).toContain('--enable-auto-tool-choice');
    const gateway = await getGateway();
    expect(gateway.optional).toBe(true);
    expect(gateway.required_for_local).toBe(false);
    expect(gateway.enabled).toBe(false);
  });

  it('returns the honest route sentence with the fixed priority', async () => {
    const route = await resolveRoute();
    expect([...route.priority]).toEqual(['hosted', 'aval', 'ollama', 'byok', 'echo']);
    expect(route.sentence_en).toContain('hosted → aval → ollama → byok → echo');
  });

  it('maps unknown-runtime errors to a stable key', () => {
    expect(mapProviderHubsError(new Error('unknown runtime')).key).toBe('errors.unknownRuntime');
  });
});
