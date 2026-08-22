/**
 * Locale resource loader.
 *
 * Locale JSON is emitted as lazy Tauri asset chunks. Startup loads English plus
 * the active locale; switching language loads only that locale. No external
 * network endpoint is involved.
 */

import type { Resource } from 'i18next';

const modules = import.meta.glob<{ default: Record<string, unknown> }>('../../locales/*/*.json');

/** Load the requested locale bundles into i18next's resource shape. */
export async function loadResources(locales: readonly string[]): Promise<Resource> {
  const requested = new Set(locales);
  const resources: Resource = {};
  await Promise.all(
    Object.entries(modules).map(async ([path, load]) => {
      const [lang, file] = path.split('/').slice(-2);
      if (!requested.has(lang)) return;
      const namespace = file.replace(/\.json$/, '');
      const module = await load();
      (resources[lang] ??= {})[namespace] = module.default;
    }),
  );
  return resources;
}
