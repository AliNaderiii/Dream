/**
 * Add-only desktop route seam.
 *
 * A domain adds one `src/routes/<domain>.tsx` file exporting `route`. Metadata
 * is read eagerly (small, declarative data); its component remains lazy and is
 * only fetched when React renders the route. Invalid or duplicate declarations
 * are omitted, so one feature cannot make the shell route table unusable.
 */

import type { ComponentType } from 'react';

export type ShellSlot = 'main';

export interface RouteDefinition {
  readonly label: string;
  readonly icon?: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  readonly path: string;
  readonly group: string;
  readonly slot?: ShellSlot;
  readonly elementLoader: () => Promise<{ default: ComponentType }>;
}

type RouteMetadata = Omit<RouteDefinition, 'elementLoader'>;
type RouteModule = { route?: RouteMetadata; default?: ComponentType };

const routeModules = import.meta.glob<RouteModule>('../routes/*.tsx', { eager: true });
const routeLoaders = import.meta.glob<RouteModule>('../routes/*.tsx');
const safePath = /^\/[a-z][a-z0-9_-]*(?:\/[a-z0-9_:-]+)*$/;

function collectRoutes(): readonly RouteDefinition[] {
  const paths = new Set<string>();
  const entries = Object.entries(routeModules).sort(([left], [right]) => left.localeCompare(right));
  const routes: RouteDefinition[] = [];
  for (const [file, module] of entries) {
    const metadata = module.route;
    const load = routeLoaders[file];
    if (
      !metadata ||
      !load ||
      !safePath.test(metadata.path) ||
      !metadata.label ||
      !metadata.group ||
      paths.has(metadata.path)
    ) {
      continue;
    }
    paths.add(metadata.path);
    routes.push({
      ...metadata,
      slot: metadata.slot ?? 'main',
      elementLoader: async () => {
        const loaded = await load();
        if (!loaded.default) throw new Error(`Route module ${file} has no default component export`);
        return { default: loaded.default };
      },
    });
  }
  return Object.freeze(routes);
}

/** Every discovered route, in deterministic filename order. */
export const registeredRoutes = collectRoutes();
/** Navigation-ready subset for shell consumers. */
export const registeredNav = Object.freeze(registeredRoutes.filter((route) => route.label.length > 0));
/** Routes grouped by shell placement; currently all extensions render in main. */
export const shellSlots: Readonly<Record<ShellSlot, readonly RouteDefinition[]>> = Object.freeze({
  main: Object.freeze(registeredRoutes.filter((route) => route.slot === 'main')),
});
