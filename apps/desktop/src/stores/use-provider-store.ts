/** Provider catalog and non-secret configuration state. */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { getBridgeClient } from '@/lib/bridge/client';
import { desktopStorage } from '@/lib/persistent-storage';
import type { Model, Provider, ProviderCatalogEntry, ProviderKind, ProviderStatus } from '@/types';

export interface ProviderDraft {
  id?: string;
  kind: Exclude<ProviderKind, 'echo'>;
  name: string;
  endpoint: string;
  modelListUrl?: string;
  models: string[];
  enabledModelIds: string[];
  oauthClientId?: string;
}

interface ProviderWire {
  id: string;
  kind: ProviderKind;
  name?: string;
  label?: string;
  status?: string;
  local?: boolean;
  endpoint?: string;
  base_url?: string;
  model_list_url?: string;
  models?: string[];
  enabled_models?: string[];
  credential_configured?: boolean;
  supports_reasoning?: boolean;
  supports_streaming?: boolean;
  last_latency_ms?: number;
  latency_ms?: number;
}

interface CatalogWire {
  name: string;
  website: string;
  docs?: string;
  auth_type: ProviderCatalogEntry['authType'];
  endpoint: string;
  model_list_url: string | null;
  supports_streaming: boolean;
  supports_reasoning: boolean;
  default_models: string[];
  oauth_supported?: boolean;
}

interface ProviderState {
  providers: Provider[];
  catalog: ProviderCatalogEntry[];
  activeProviderId: string | null;
  activeModelId: string | null;
  loading: boolean;
  error: string | null;

  load: () => Promise<void>;
  setActiveProvider: (id: string) => void;
  setActiveModel: (modelId: string) => void;
  setProviderStatus: (id: string, status: ProviderStatus, latencyMs?: number) => void;
  saveProvider: (draft: ProviderDraft, credential?: string) => Promise<Provider>;
  removeProvider: (id: string) => Promise<void>;
  fetchModels: (id: string, force?: boolean) => Promise<string[]>;
  testProvider: (id: string) => Promise<{ ok: boolean; detail?: string; latencyMs?: number }>;
  setModelEnabled: (providerId: string, modelId: string, enabled: boolean) => Promise<void>;
  activeProvider: () => Provider | undefined;
}

const ECHO_PROVIDER: Provider = {
  id: 'echo',
  name: 'Echo (offline)',
  kind: 'echo',
  status: 'connected',
  local: true,
  models: [{ id: 'echo', name: 'Echo', providerId: 'echo' }],
  enabledModelIds: ['echo'],
  credentialConfigured: true,
  supportsReasoning: false,
  supportsStreaming: true,
};

function asModels(providerId: string, models: string[]): Model[] {
  return models.map((model) => ({ id: model, name: model, providerId }));
}

function providerFromWire(wire: ProviderWire): Provider {
  const models = wire.models ?? [];
  const status: ProviderStatus =
    wire.status === 'connected' ? 'connected' : wire.status === 'error' ? 'error' : 'disconnected';
  return {
    id: wire.id,
    name: wire.name ?? wire?.label ?? wire.id,
    kind: wire.kind,
    status,
    local: Boolean(wire.local),
    endpoint: wire.endpoint ?? wire.base_url,
    modelListUrl: wire.model_list_url,
    models: asModels(wire.id, models),
    enabledModelIds: wire.enabled_models ?? models,
    credentialConfigured: wire.credential_configured,
    supportsReasoning: wire.supports_reasoning,
    supportsStreaming: wire.supports_streaming,
    latencyMs: wire.last_latency_ms ?? wire.latency_ms,
  };
}

function draftWire(draft: ProviderDraft) {
  return {
    kind: draft.kind,
    name: draft.name,
    endpoint: draft.endpoint,
    model_list_url: draft.modelListUrl,
    models: draft.models,
    enabled_models: draft.enabledModelIds,
    oauth_client_id: draft.oauthClientId,
  };
}

export const useProviderStore = create<ProviderState>()(
  persist(
    (set, get) => ({
      providers: [ECHO_PROVIDER],
      catalog: [],
      activeProviderId: 'echo',
      activeModelId: 'echo',
      loading: false,
      error: null,

      load: async () => {
        set({ loading: true, error: null });
        try {
          const client = getBridgeClient();
          const [catalogResult, providerResult] = await Promise.all([
            client.call<{ catalog: Record<string, CatalogWire> }>('provider.catalog'),
            client.call<{ providers: ProviderWire[]; default: string }>('provider.list'),
          ]);
          const catalog = Object.entries(catalogResult.catalog).map(([id, entry]) => ({
            id: id as ProviderCatalogEntry['id'],
            name: entry.name,
            website: entry.website,
            docs: entry.docs,
            authType: entry.auth_type,
            endpoint: entry.endpoint,
            modelListUrl: entry.model_list_url,
            supportsStreaming: entry.supports_streaming,
            supportsReasoning: entry.supports_reasoning,
            defaultModels: entry.default_models,
            oauthSupported: entry.oauth_supported,
          }));
          const providers = providerResult.providers.map(providerFromWire);
          const activeProviderId = providers.some((p) => p.id === get().activeProviderId)
            ? get().activeProviderId
            : (providerResult.default ?? providers[0]?.id ?? 'echo');
          const active = providers.find((p) => p.id === activeProviderId);
          set({
            catalog,
            providers,
            activeProviderId,
            activeModelId:
              active?.enabledModelIds.includes(get().activeModelId ?? '') === true
                ? get().activeModelId
                : (active?.enabledModelIds[0] ?? null),
            loading: false,
          });
        } catch {
          // Browser fallback and a temporarily restarting sidecar remain useful.
          set({
            loading: false,
            error: 'Could not load providers. The saved list is still available.',
          });
        }
      },

      setActiveProvider: (activeProviderId) => {
        const provider = get().providers.find((p) => p.id === activeProviderId);
        set({ activeProviderId, activeModelId: provider?.enabledModelIds[0] ?? null });
      },

      setActiveModel: (activeModelId) => set({ activeModelId }),

      setProviderStatus: (id, status, latencyMs) =>
        set((state) => ({
          providers: state.providers.map((provider) =>
            provider.id === id
              ? { ...provider, status, ...(latencyMs === undefined ? {} : { latencyMs }) }
              : provider,
          ),
        })),

      saveProvider: async (draft, credential) => {
        const client = getBridgeClient();
        const exists = Boolean(
          draft.id && get().providers.some((provider) => provider.id === draft.id),
        );
        const result = await client.call<{ provider: ProviderWire }>(
          exists ? 'provider.update' : 'provider.create',
          {
            ...(draft.id ? { id: draft.id } : {}),
            provider: draftWire(draft),
            ...(credential ? { credential } : {}),
          },
        );
        const provider = providerFromWire(result.provider);
        set((state) => ({
          providers: exists
            ? state.providers.map((item) => (item.id === provider.id ? provider : item))
            : [...state.providers, provider],
        }));
        return provider;
      },

      removeProvider: async (id) => {
        await getBridgeClient().call('provider.delete', { id });
        set((state) => {
          const providers = state.providers.filter((provider) => provider.id !== id);
          const fallback = providers[0] ?? ECHO_PROVIDER;
          return {
            providers,
            activeProviderId: state.activeProviderId === id ? fallback.id : state.activeProviderId,
            activeModelId:
              state.activeProviderId === id
                ? (fallback.enabledModelIds[0] ?? null)
                : state.activeModelId,
          };
        });
      },

      fetchModels: async (id, force = true) => {
        const result = await getBridgeClient().call<{ models: string[]; error?: string }>(
          'provider.models',
          { id, force },
        );
        if (result.error) throw new Error(result.error);
        set((state) => ({
          providers: state.providers.map((provider) =>
            provider.id === id
              ? {
                  ...provider,
                  models: asModels(id, result.models),
                  enabledModelIds:
                    provider.enabledModelIds.filter((model) => result.models.includes(model))
                      .length > 0
                      ? provider.enabledModelIds.filter((model) => result.models.includes(model))
                      : result.models,
                }
              : provider,
          ),
        }));
        return result.models;
      },

      testProvider: async (id) => {
        get().setProviderStatus(id, 'testing');
        try {
          const result = await getBridgeClient().call<{
            ok: boolean;
            detail?: string;
            latency_ms?: number;
          }>('provider.test', { id });
          get().setProviderStatus(id, result.ok ? 'connected' : 'error', result.latency_ms);
          return { ok: result.ok, detail: result.detail, latencyMs: result.latency_ms };
        } catch {
          get().setProviderStatus(id, 'error');
          return { ok: false, detail: 'Connection failed' };
        }
      },

      setModelEnabled: async (providerId, modelId, enabled) => {
        const provider = get().providers.find((item) => item.id === providerId);
        if (!provider || provider.kind === 'echo') return;
        const enabledModelIds = enabled
          ? [...new Set([...provider.enabledModelIds, modelId])]
          : provider.enabledModelIds.filter((id) => id !== modelId);
        const draft: ProviderDraft = {
          id: provider.id,
          kind: provider.kind,
          name: provider.name,
          endpoint: provider.endpoint ?? '',
          modelListUrl: provider.modelListUrl,
          models: provider.models.map((model) => model.id),
          enabledModelIds,
        };
        await get().saveProvider(draft);
      },

      activeProvider: () => get().providers.find((p) => p.id === get().activeProviderId),
    }),
    {
      name: 'dream.providers.v2',
      storage: createJSONStorage(() => desktopStorage),
      // Catalog and status are refreshed through the bridge. Persist only safe
      // metadata; Provider has no credential field by construction.
      partialize: (state) => ({
        providers: state.providers.map((provider) => ({
          ...provider,
          status: provider.kind === 'echo' ? ('connected' as const) : ('disconnected' as const),
          latencyMs: undefined,
        })),
        activeProviderId: state.activeProviderId,
        activeModelId: state.activeModelId,
      }),
      version: 2,
    },
  ),
);
