/** Add-only, lazy desktop route discovery for new domain pages. */

import type { ComponentType } from 'react';

export type ShellSlot = 'main';

type RouteIcon = ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;

export interface RouteDefinition {
  readonly label: string;
  readonly icon?: RouteIcon;
  readonly path: string;
  readonly group: string;
  readonly slot: ShellSlot;
  readonly elementLoader: () => Promise<{ default: ComponentType }>;
}

type RouteMetadata = Partial<Pick<RouteDefinition, 'label' | 'icon' | 'path' | 'group' | 'slot'>>;
type RouteModule = { default?: ComponentType };
type MetadataModule = { route?: RouteMetadata };

const routeLoaders = import.meta.glob<RouteModule>(['../routes/*.tsx', '!../routes/*.test.tsx']);
// Metadata is small declarative data. Page components are never eagerly loaded.
const metadataModules = import.meta.glob<MetadataModule>('../routes/*.route.ts', { eager: true });

const DENYLIST = new Set([
  'dashboard',
  'chat',
  'connectivity',
  'data',
  'data.dataset',
  'memory',
  'projects',
  'provenance',
  'providers',
  'scheduler',
  'settings',
  'skills',
  'subagents',
]);
const RESERVED_PATHS = new Set([
  '/',
  '/chat',
  '/chat/:sessionId',
  '/memory',
  '/skills',
  '/projects',
  '/scheduler',
  '/subagents',
  '/provenance',
  '/data',
  '/data/:datasetId',
  '/connectivity',
  '/providers',
  '/settings',
]);
const DOMAIN = /^[a-z][a-z0-9_]*$/;
const SAFE_PATH = /^\/[a-z][a-z0-9_-]*(?:\/[a-z0-9_:-]+)*$/;

function domainFromRouteFile(file: string): string | null {
  const filename =
    file
      .split('/')
      .at(-1)
      ?.replace(/\.tsx$/, '') ?? '';
  return DOMAIN.test(filename) && !DENYLIST.has(filename) ? filename : null;
}

function metadataFor(domain: string): RouteMetadata {
  return metadataModules[`../routes/${domain}.route.ts`]?.route ?? {};
}

function collectRoutes(): readonly RouteDefinition[] {
  const paths = new Set<string>();
  const routes: RouteDefinition[] = [];
  for (const [file, load] of Object.entries(routeLoaders).sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    const domain = domainFromRouteFile(file);
    if (!domain) continue;
    const metadata = metadataFor(domain);
    const path = metadata.path ?? `/${domain}`;
    if (!SAFE_PATH.test(path) || RESERVED_PATHS.has(path) || paths.has(path)) continue;
    paths.add(path);
    routes.push({
      label: metadata.label ?? `nav.${domain}`,
      ...(metadata.icon ? { icon: metadata.icon } : {}),
      path,
      group: metadata.group ?? 'workspace',
      slot: metadata.slot ?? 'main',
      elementLoader: async () => {
        const loaded = await load();
        if (!loaded.default)
          throw new Error(`Route module ${file} has no default component export`);
        return { default: loaded.default };
      },
    });
  }
  return Object.freeze(routes);
}

/** New extension pages only; existing pages remain in App.tsx's static table. */
export const registeredRoutes = collectRoutes();
export const registeredNav = Object.freeze(
  registeredRoutes.filter((route) => route.label.length > 0),
);
export const shellSlots: Readonly<Record<ShellSlot, readonly RouteDefinition[]>> = Object.freeze({
  main: Object.freeze(registeredRoutes.filter((route) => route.slot === 'main')),
});
