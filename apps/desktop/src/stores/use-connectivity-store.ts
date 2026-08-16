/**
 * Connectivity gateway state.
 *
 * Every action goes through the bridge (`gateway.*` RPCs), so the store is a
 * thin typed cache: load the catalog + status, configure platforms, issue
 * link codes, read the message log. In `npm run dev` the echo transport
 * answers the same methods, so this store works with no sidecar running.
 */

import { create } from 'zustand';

import { getBridgeClient } from '@/lib/bridge/client';
import type {
  GatewayLinkCodeResult,
  GatewayLogsResult,
  GatewayPlatform,
  GatewayPlatformName,
  GatewayStatusResult,
} from '@/lib/bridge/types';

interface ConnectivityState {
  /** Platform catalog joined with public config (gateway.platforms). */
  platforms: GatewayPlatform[];
  /** Aggregate gateway status (gateway.status). */
  status: GatewayStatusResult | null;
  /** Message-log rows for the selected platform (gateway.logs). */
  logs: GatewayLogsResult | null;
  /** Pending link codes keyed by platform. */
  linkCodes: Record<string, GatewayLinkCodeResult>;
  /** The platform whose configure form is expanded. */
  expandedPlatform: GatewayPlatformName | null;
  loading: boolean;
  error: string | null;

  load: () => Promise<void>;
  startGateway: () => Promise<void>;
  stopGateway: () => Promise<void>;
  configure: (platform: GatewayPlatformName, config: Record<string, unknown>) => Promise<void>;
  fetchLogs: (platform: GatewayPlatformName | null) => Promise<void>;
  issueLinkCode: (platform: GatewayPlatformName) => Promise<void>;
  unlinkUser: (platform: GatewayPlatformName, userId: string) => Promise<void>;
  setExpandedPlatform: (platform: GatewayPlatformName | null) => void;
}

/** Run one bridge call, mapping failures into the store's error field. */
async function guarded<T>(
  fn: () => Promise<T>,
  set: (update: Partial<ConnectivityState>) => void,
): Promise<T | null> {
  try {
    set({ error: null });
    return await fn();
  } catch (err) {
    set({ error: err instanceof Error ? err.message : String(err) });
    return null;
  }
}

export const useConnectivityStore = create<ConnectivityState>()((set) => ({
  platforms: [],
  status: null,
  logs: null,
  linkCodes: {},
  expandedPlatform: null,
  loading: false,
  error: null,

  load: async () => {
    const bridge = getBridgeClient();
    set({ loading: true });
    const [platforms, status] = await Promise.all([
      guarded(
        async () =>
          (await bridge.call<{ platforms: GatewayPlatform[] }>('gateway.platforms')).platforms,
        set,
      ),
      guarded(async () => bridge.call<GatewayStatusResult>('gateway.status'), set),
    ]);
    set({
      loading: false,
      platforms: platforms ?? [],
      status,
    });
  },

  startGateway: async () => {
    const bridge = getBridgeClient();
    const status = await guarded(() => bridge.call<GatewayStatusResult>('gateway.start'), set);
    if (status) set({ status });
    await useConnectivityStore.getState().load();
  },

  stopGateway: async () => {
    const bridge = getBridgeClient();
    const status = await guarded(() => bridge.call<GatewayStatusResult>('gateway.stop'), set);
    if (status) set({ status });
    await useConnectivityStore.getState().load();
  },

  configure: async (platform, config) => {
    const bridge = getBridgeClient();
    await guarded(() => bridge.call('gateway.configure', { platform, config }), set);
    await useConnectivityStore.getState().load();
  },

  fetchLogs: async (platform) => {
    const bridge = getBridgeClient();
    const logs = await guarded(
      () => bridge.call<GatewayLogsResult>('gateway.logs', { platform, limit: 100 }),
      set,
    );
    if (logs) set({ logs });
  },

  issueLinkCode: async (platform) => {
    const bridge = getBridgeClient();
    const code = await guarded(
      () => bridge.call<GatewayLinkCodeResult>('gateway.link_code', { platform }),
      set,
    );
    if (code) {
      set((state) => ({ linkCodes: { ...state.linkCodes, [platform]: code } }));
    }
  },

  unlinkUser: async (platform, userId) => {
    const bridge = getBridgeClient();
    await guarded(() => bridge.call('gateway.unlink_user', { platform, user_id: userId }), set);
    await useConnectivityStore.getState().load();
  },

  setExpandedPlatform: (platform) => set({ expandedPlatform: platform }),
}));
