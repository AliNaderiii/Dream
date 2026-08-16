import { beforeEach, describe, expect, it } from 'vitest';

import { resetBridgeClient } from '@/lib/bridge/client';
import { useConnectivityStore } from '@/stores/use-connectivity-store';

describe('useConnectivityStore', () => {
  beforeEach(() => {
    resetBridgeClient();
    useConnectivityStore.setState({
      platforms: [],
      status: null,
      logs: null,
      linkCodes: {},
      expandedPlatform: null,
      loading: false,
      error: null,
    });
  });

  it('loads the platform catalog and gateway status through the bridge', async () => {
    await useConnectivityStore.getState().load();
    const { platforms, status } = useConnectivityStore.getState();
    expect(platforms.map((p) => p.name)).toEqual([
      'telegram',
      'discord',
      'slack',
      'whatsapp',
      'signal',
      'email',
    ]);
    expect(status?.running).toBe(false);
    expect(status?.adapters).toHaveLength(6);
    expect(useConnectivityStore.getState().error).toBeNull();
  });

  it('configures a platform with redacted secrets and refreshes the catalog', async () => {
    await useConnectivityStore.getState().load();
    await useConnectivityStore
      .getState()
      .configure('telegram', { token: '123456:ABCDEF', enabled: true });
    const telegram = useConnectivityStore.getState().platforms.find((p) => p.name === 'telegram');
    expect(telegram?.enabled).toBe(true);
    expect(telegram?.configured).toBe(true);
    expect(useConnectivityStore.getState().error).toBeNull();
  });

  it('starts and stops the gateway, updating status', async () => {
    await useConnectivityStore.getState().load();
    await useConnectivityStore.getState().startGateway();
    expect(useConnectivityStore.getState().status?.running).toBe(true);
    await useConnectivityStore.getState().stopGateway();
    expect(useConnectivityStore.getState().status?.running).toBe(false);
  });

  it('issues a link code for one platform', async () => {
    await useConnectivityStore.getState().issueLinkCode('slack');
    const code = useConnectivityStore.getState().linkCodes['slack'];
    expect(code).toBeDefined();
    expect(code?.code).toMatch(/^\d{6}$/);
    expect(code?.platform).toBe('slack');
  });

  it('fetches the message log for one platform', async () => {
    await useConnectivityStore.getState().fetchLogs('email');
    const logs = useConnectivityStore.getState().logs;
    expect(logs?.entries.length).toBeGreaterThan(0);
    expect(logs?.entries.every((entry) => entry.platform === 'email')).toBe(true);
  });

  it('tracks the expanded platform locally', () => {
    useConnectivityStore.getState().setExpandedPlatform('discord');
    expect(useConnectivityStore.getState().expandedPlatform).toBe('discord');
    useConnectivityStore.getState().setExpandedPlatform(null);
    expect(useConnectivityStore.getState().expandedPlatform).toBeNull();
  });
});
