/**
 * Locale resource loader.
 *
 * The desktop shell is bundled by Tauri and served from the `tauri://localhost`
 * asset protocol, so translations are imported eagerly at build time rather
 * than fetched over HTTP. `import.meta.glob` assembles every
 * `locales/<lang>/<namespace>.json` into the `{ [lang]: { [namespace]: … } }`
 * shape i18next expects.
 */

import type { Resource } from 'i18next';

const modules = import.meta.glob<{ default: Record<string, unknown> }>('../../locales/*/*.json', {
  eager: true,
});

/** Build the i18next resource tree from the eager locale imports. */
export function loadResources(): Resource {
  const resources: Resource = {};
  for (const [path, module] of Object.entries(modules)) {
    // Path is `…/locales/<lang>/<namespace>.json`.
    const [lang, file] = path.split('/').slice(-2);
    const namespace = file.replace(/\.json$/, '');
    (resources[lang] ??= {})[namespace] = module.default;
  }
  return resources;
}
