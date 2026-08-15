/**
 * Model provider configuration.
 *
 * Seeded with the backends the Python core already implements (`docs/ARCHITECTURE.md`
 * §Backends). Connection testing and credential storage land with the bridge in P-02;
 * API keys are never held in this store — they belong in the OS keychain.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Provider, ProviderStatus } from '@/types';

interface ProviderState {
  providers: Provider[];
  activeProviderId: string | null;
  activeModelId: string | null;

  setActiveProvider: (id: string) => void;
  setActiveModel: (modelId: string) => void;
  setProviderStatus: (id: string, status: ProviderStatus, latencyMs?: number) => void;
  addProvider: (provider: Provider) => void;
  removeProvider: (id: string) => void;
  /** The currently selected provider, if any. */
  activeProvider: () => Provider | undefined;
}

/** Providers that mirror the Python core's built-in backends. */
const DEFAULT_PROVIDERS: Provider[] = [
  {
    id: 'ollama',
    name: 'Ollama',
    kind: 'ollama',
    status: 'disconnected',
    local: true,
    baseUrl: 'http://localhost:11434',
    models: [],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    kind: 'openai',
    status: 'disconnected',
    local: false,
    models: [],
  },
  {
    id: 'echo',
    name: 'Echo (offline)',
    kind: 'echo',
    status: 'connected',
    local: true,
    models: [{ id: 'echo', name: 'Echo', providerId: 'echo' }],
  },
];

export const useProviderStore = create<ProviderState>()(
  persist(
    (set, get) => ({
      providers: DEFAULT_PROVIDERS,
      activeProviderId: 'echo',
      activeModelId: 'echo',

      setActiveProvider: (activeProviderId) => {
        const provider = get().providers.find((p) => p.id === activeProviderId);
        set({ activeProviderId, activeModelId: provider?.models[0]?.id ?? null });
      },

      setActiveModel: (activeModelId) => set({ activeModelId }),

      setProviderStatus: (id, status, latencyMs) =>
        set((state) => ({
          providers: state.providers.map((p) =>
            p.id === id ? { ...p, status, ...(latencyMs === undefined ? {} : { latencyMs }) } : p,
          ),
        })),

      addProvider: (provider) => set((state) => ({ providers: [...state.providers, provider] })),

      removeProvider: (id) =>
        set((state) => ({
          providers: state.providers.filter((p) => p.id !== id),
          activeProviderId: state.activeProviderId === id ? null : state.activeProviderId,
        })),

      activeProvider: () => get().providers.find((p) => p.id === get().activeProviderId),
    }),
    {
      name: 'dream.providers',
      // Transient connection results are recomputed on launch, never restored.
      partialize: (state) => ({
        providers: state.providers.map((p) => ({
          ...p,
          status: 'disconnected' as const,
          latencyMs: undefined,
        })),
        activeProviderId: state.activeProviderId,
        activeModelId: state.activeModelId,
      }),
    },
  ),
);
