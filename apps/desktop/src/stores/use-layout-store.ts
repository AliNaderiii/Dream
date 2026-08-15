/** Persistent recursive split-pane and virtual-screen state. */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { desktopStorage } from '@/lib/persistent-storage';

export type PaneType = 'chat' | 'subagent' | 'file' | 'data';
export type SplitDirection = 'horizontal' | 'vertical';
export type DockEdge = 'left' | 'right' | 'top' | 'bottom';

export interface PaneState {
  id: string;
  type: PaneType;
  sessionId: string | null;
  providerId: string;
  modelName: string;
  reasoningEffort: number;
  layout: { direction: SplitDirection; ratio: number };
}

export interface PaneLeaf {
  kind: 'pane';
  pane: PaneState;
}

export interface PaneSplit {
  kind: 'split';
  id: string;
  direction: SplitDirection;
  ratio: number;
  first: LayoutNode;
  second: LayoutNode;
}

export type LayoutNode = PaneLeaf | PaneSplit;

export interface ScreenState {
  id: string;
  name: string;
  root: LayoutNode;
  activePaneId: string;
  maximizedPaneId: string | null;
}

interface LayoutState {
  screens: ScreenState[];
  activeScreenId: string;
  hydrated: boolean;

  setHydrated: (hydrated: boolean) => void;
  setActiveScreen: (id: string) => void;
  addScreen: (name?: string) => string;
  renameScreen: (id: string, name: string) => void;
  removeScreen: (id: string) => void;
  setActivePane: (paneId: string) => void;
  addPane: (targetPaneId: string, direction: SplitDirection, pane?: Partial<PaneState>) => string;
  closePane: (paneId: string) => void;
  toggleMaximize: (paneId: string) => void;
  resizeSplit: (splitId: string, ratio: number) => void;
  updatePane: (paneId: string, changes: Partial<Omit<PaneState, 'id'>>) => void;
  dockPane: (paneId: string, targetPaneId: string, edge: DockEdge) => void;
  movePaneToScreen: (paneId: string, screenId: string) => void;
  assignSession: (sessionId: string) => void;
  resetLayout: () => void;
}

let idCounter = 0;
export function layoutId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  idCounter += 1;
  return `${prefix}-${Date.now()}-${idCounter}`;
}

export function createPane(overrides: Partial<PaneState> = {}): PaneState {
  return {
    id: overrides.id ?? layoutId('pane'),
    type: overrides.type ?? 'chat',
    sessionId: overrides.sessionId ?? null,
    providerId: overrides.providerId ?? 'echo',
    modelName: overrides.modelName ?? 'echo',
    reasoningEffort: overrides.reasoningEffort ?? 0,
    layout: overrides.layout ?? { direction: 'horizontal', ratio: 0.5 },
  };
}

export function paneLeaf(pane: PaneState): PaneLeaf {
  return { kind: 'pane', pane };
}

function newScreen(index = 1): ScreenState {
  const pane = createPane();
  return {
    id: layoutId('screen'),
    name: `Screen ${index}`,
    root: paneLeaf(pane),
    activePaneId: pane.id,
    maximizedPaneId: null,
  };
}

export function findPane(node: LayoutNode, paneId: string): PaneState | undefined {
  if (node.kind === 'pane') return node.pane.id === paneId ? node.pane : undefined;
  return findPane(node.first, paneId) ?? findPane(node.second, paneId);
}

export function firstPane(node: LayoutNode): PaneState {
  return node.kind === 'pane' ? node.pane : firstPane(node.first);
}

export function mapPane(
  node: LayoutNode,
  paneId: string,
  map: (pane: PaneState) => PaneState,
): LayoutNode {
  if (node.kind === 'pane') {
    return node.pane.id === paneId ? paneLeaf(map(node.pane)) : node;
  }
  return {
    ...node,
    first: mapPane(node.first, paneId, map),
    second: mapPane(node.second, paneId, map),
  };
}

export function splitAtPane(
  node: LayoutNode,
  targetPaneId: string,
  newPane: PaneState,
  direction: SplitDirection,
  before = false,
): LayoutNode {
  if (node.kind === 'pane') {
    if (node.pane.id !== targetPaneId) return node;
    const added = paneLeaf(newPane);
    return {
      kind: 'split',
      id: layoutId('split'),
      direction,
      ratio: 0.5,
      first: before ? added : node,
      second: before ? node : added,
    };
  }
  return {
    ...node,
    first: splitAtPane(node.first, targetPaneId, newPane, direction, before),
    second: splitAtPane(node.second, targetPaneId, newPane, direction, before),
  };
}

/** Remove a leaf and collapse its now-unary parent. */
export function removePane(node: LayoutNode, paneId: string): LayoutNode | null {
  if (node.kind === 'pane') return node.pane.id === paneId ? null : node;
  const first = removePane(node.first, paneId);
  const second = removePane(node.second, paneId);
  if (!first) return second;
  if (!second) return first;
  return { ...node, first, second };
}

export function resizeNode(node: LayoutNode, splitId: string, ratio: number): LayoutNode {
  if (node.kind === 'pane') return node;
  return {
    ...node,
    ratio: node.id === splitId ? Math.min(0.9, Math.max(0.1, ratio)) : node.ratio,
    first: resizeNode(node.first, splitId, ratio),
    second: resizeNode(node.second, splitId, ratio),
  };
}

export function countPanes(node: LayoutNode): number {
  return node.kind === 'pane' ? 1 : countPanes(node.first) + countPanes(node.second);
}

const initialScreen = newScreen();
const initialState = { screens: [initialScreen], activeScreenId: initialScreen.id };

function screenContaining(screens: ScreenState[], paneId: string): ScreenState | undefined {
  return screens.find((screen) => findPane(screen.root, paneId));
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set, get) => ({
      ...initialState,
      hydrated: false,
      setHydrated: (hydrated) => set({ hydrated }),

      setActiveScreen: (activeScreenId) => {
        if (get().screens.some((screen) => screen.id === activeScreenId)) set({ activeScreenId });
      },

      addScreen: (name) => {
        const screen = newScreen(get().screens.length + 1);
        if (name?.trim()) screen.name = name.trim();
        set((state) => ({ screens: [...state.screens, screen], activeScreenId: screen.id }));
        return screen.id;
      },

      renameScreen: (id, name) =>
        set((state) => ({
          screens: state.screens.map((screen) =>
            screen.id === id && name.trim() ? { ...screen, name: name.trim() } : screen,
          ),
        })),

      removeScreen: (id) =>
        set((state) => {
          if (state.screens.length === 1) return state;
          const screens = state.screens.filter((screen) => screen.id !== id);
          return {
            screens,
            activeScreenId:
              state.activeScreenId === id
                ? (screens[0]?.id ?? state.activeScreenId)
                : state.activeScreenId,
          };
        }),

      setActivePane: (paneId) =>
        set((state) => {
          const owner = screenContaining(state.screens, paneId);
          if (!owner) return state;
          return {
            activeScreenId: owner.id,
            screens: state.screens.map((screen) =>
              screen.id === owner.id ? { ...screen, activePaneId: paneId } : screen,
            ),
          };
        }),

      addPane: (targetPaneId, direction, overrides) => {
        const pane = createPane({ layout: { direction, ratio: 0.5 }, ...overrides });
        set((state) => ({
          screens: state.screens.map((screen) =>
            findPane(screen.root, targetPaneId)
              ? {
                  ...screen,
                  root: splitAtPane(screen.root, targetPaneId, pane, direction),
                  activePaneId: pane.id,
                  maximizedPaneId: null,
                }
              : screen,
          ),
        }));
        return pane.id;
      },

      closePane: (paneId) =>
        set((state) => ({
          screens: state.screens.map((screen) => {
            if (!findPane(screen.root, paneId)) return screen;
            const root = removePane(screen.root, paneId);
            if (!root) {
              const replacement = createPane();
              return { ...screen, root: paneLeaf(replacement), activePaneId: replacement.id };
            }
            return {
              ...screen,
              root,
              activePaneId:
                screen.activePaneId === paneId ? firstPane(root).id : screen.activePaneId,
              maximizedPaneId: screen.maximizedPaneId === paneId ? null : screen.maximizedPaneId,
            };
          }),
        })),

      toggleMaximize: (paneId) =>
        set((state) => ({
          screens: state.screens.map((screen) =>
            findPane(screen.root, paneId)
              ? {
                  ...screen,
                  activePaneId: paneId,
                  maximizedPaneId: screen.maximizedPaneId === paneId ? null : paneId,
                }
              : screen,
          ),
        })),

      resizeSplit: (splitId, ratio) =>
        set((state) => ({
          screens: state.screens.map((screen) => ({
            ...screen,
            root: resizeNode(screen.root, splitId, ratio),
          })),
        })),

      updatePane: (paneId, changes) =>
        set((state) => ({
          screens: state.screens.map((screen) => ({
            ...screen,
            root: mapPane(screen.root, paneId, (pane) => ({ ...pane, ...changes })),
          })),
        })),

      dockPane: (paneId, targetPaneId, edge) => {
        if (paneId === targetPaneId) return;
        set((state) => {
          const source = screenContaining(state.screens, paneId);
          const target = screenContaining(state.screens, targetPaneId);
          if (!source || !target) return state;
          const moving = findPane(source.root, paneId);
          if (!moving) return state;
          const direction: SplitDirection =
            edge === 'left' || edge === 'right' ? 'horizontal' : 'vertical';
          const before = edge === 'left' || edge === 'top';
          let screens = state.screens.map((screen) => {
            if (screen.id !== source.id) return screen;
            const root = removePane(screen.root, paneId);
            if (root)
              return { ...screen, root, activePaneId: firstPane(root).id, maximizedPaneId: null };
            const replacement = createPane();
            return {
              ...screen,
              root: paneLeaf(replacement),
              activePaneId: replacement.id,
              maximizedPaneId: null,
            };
          });
          screens = screens.map((screen) =>
            screen.id === target.id
              ? {
                  ...screen,
                  root: splitAtPane(screen.root, targetPaneId, moving, direction, before),
                  activePaneId: moving.id,
                  maximizedPaneId: null,
                }
              : screen,
          );
          return { screens, activeScreenId: target.id };
        });
      },

      movePaneToScreen: (paneId, screenId) => {
        const target = get().screens.find((screen) => screen.id === screenId);
        if (!target || findPane(target.root, paneId)) {
          if (target) set({ activeScreenId: target.id });
          return;
        }
        get().dockPane(paneId, target.activePaneId, 'right');
      },

      assignSession: (sessionId) =>
        set((state) => {
          const screen = state.screens.find((item) => item.id === state.activeScreenId);
          if (!screen) return state;
          return {
            screens: state.screens.map((item) =>
              item.id === screen.id
                ? {
                    ...item,
                    root: mapPane(item.root, item.activePaneId, (pane) => ({
                      ...pane,
                      type: 'chat',
                      sessionId,
                    })),
                  }
                : item,
            ),
          };
        }),

      resetLayout: () => {
        const screen = newScreen();
        set({ screens: [screen], activeScreenId: screen.id });
      },
    }),
    {
      name: 'dream.layout.v1',
      storage: createJSONStorage(() => desktopStorage),
      partialize: (state) => ({ screens: state.screens, activeScreenId: state.activeScreenId }),
      version: 1,
      onRehydrateStorage: () => (state) => state?.setHydrated(true),
    },
  ),
);
