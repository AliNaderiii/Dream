/** Auto-discovered locale namespaces, kept in sync with locale JSON files. */

const localeModules = import.meta.glob('../../locales/*/*.json', { eager: true });
const namespaceName = /^[a-z][a-z0-9_-]*$/;

/**
 * Namespace names discovered from bundled locale JSON, sorted and de-duplicated.
 * The existing resource loader uses the same glob and therefore loads every
 * listed namespace for each requested locale without a hand-maintained list.
 */
export const registeredNamespaces: readonly string[] = Object.freeze(
  [...new Set(
    Object.keys(localeModules)
      .map((path) => path.split('/').at(-1)?.replace(/\.json$/, '') ?? '')
      .filter((name) => namespaceName.test(name)),
  )].sort(),
);
