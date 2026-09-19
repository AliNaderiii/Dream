/**
 * Workspace path joining (v4.4).
 *
 * Pure helpers for composing the absolute path of a workspace entry from its
 * root record and the backend's forward-slash relative path. Kept out of the
 * component file so fast refresh stays intact and the logic is unit-testable.
 */

/**
 * Join a root's absolute path with a forward-slash relative entry path.
 * Windows roots keep backslashes; accidental double separators are avoided.
 */
export function joinWorkspacePath(rootPath: string, rel: string): string {
  const cleanRoot = rootPath.trim().replace(/[\\/]+$/, '');
  const cleanRel = rel.trim().replace(/^[\\/]+/, '');
  if (!cleanRel) return cleanRoot || '/';
  if (!cleanRoot) return `/${cleanRel}`;
  const sep = cleanRoot.includes('\\') && !cleanRoot.includes('/') ? '\\' : '/';
  const normalizedRel = cleanRel.replace(/[\\/]+/g, sep);
  return `${cleanRoot}${sep}${normalizedRel}`;
}
