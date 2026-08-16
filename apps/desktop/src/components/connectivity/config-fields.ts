/**
 * Pure form helpers for the per-platform configure form.
 *
 * Kept free of JSX so they are unit-testable without a renderer: catalog
 * defaults seed the form, raw input strings coerce back to the typed values
 * `gateway.configure` expects, and secrets never round-trip into the form
 * (the sidecar only ever replies with a redacted view).
 */

import type { GatewayPlatform } from '@/lib/bridge/types';

/** Initial form values: catalog defaults for missing keys (no secret echo-back). */
export function initialConfig(platform: GatewayPlatform): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of platform.fields) {
    if (field.default !== undefined) values[field.key] = field.default;
    else if (field.type === 'boolean') values[field.key] = false;
    else values[field.key] = '';
  }
  return values;
}

/** Coerce raw form strings back into the types `gateway.configure` expects. */
export function coerceFieldValues(
  platform: GatewayPlatform,
  raw: Record<string, unknown>,
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of platform.fields) {
    const value = raw[field.key];
    if (field.type === 'number') {
      const parsed = Number(value);
      values[field.key] = Number.isFinite(parsed) ? parsed : (field.default ?? null);
    } else if (field.type === 'boolean') {
      values[field.key] = value === true || value === 'true';
    } else {
      values[field.key] = typeof value === 'string' ? value.trim() : value;
    }
  }
  return values;
}

/** Render one raw form value as text for an input's `value` attribute. */
export function fieldAsText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}
