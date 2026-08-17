/**
 * Per-platform configure form.
 *
 * Field specs come from the platform catalog; secret fields render as
 * password inputs hidden by default with a per-field reveal toggle. Saving
 * goes through `gateway.configure`, which keeps secrets on the sidecar and
 * returns a redacted view.
 */

import { Eye, EyeOff, Save } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  coerceFieldValues,
  fieldAsText,
  initialConfig,
} from '@/components/connectivity/config-fields';
import { Button } from '@/components/ui/button';
import type { GatewayPlatform } from '@/lib/bridge/types';

interface PlatformConfigProps {
  platform: GatewayPlatform;
  onSave: (config: Record<string, unknown>) => void;
}

export function PlatformConfig({ platform, onSave }: PlatformConfigProps) {
  const [values, setValues] = useState<Record<string, unknown>>(() => initialConfig(platform));
  const [revealed, setRevealed] = useState<Set<string>>(() => new Set());

  // Re-initialise the form when the platform changes (keyed by platform name
  // from the parent, so this component remounts instead of leaking state).
  const fieldValues = useMemo(() => values, [values]);

  const toggleReveal = (key: string) => {
    setRevealed((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const inputType = (type: string, key: string, secret: boolean | undefined) => {
    if (type === 'number') return 'number';
    if (secret && !revealed.has(key)) return 'password';
    return 'text';
  };

  return (
    <form
      className="flex flex-col gap-3 border-t border-border-default pt-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(coerceFieldValues(platform, fieldValues));
      }}
      aria-label={`${platform?.label} configuration`}
    >
      {platform.fields.map((field) => {
        const secret = field.type === 'secret';
        if (field.type === 'boolean') {
          return (
            <label key={field.key} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={fieldValues[field.key] === true}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.key]: event.target.checked }))
                }
                className="size-4 accent-accent"
              />
              <span className="text-caption font-medium text-fg-secondary">{field?.label}</span>
            </label>
          );
        }
        return (
          <label key={field.key} className="flex flex-col gap-1">
            <span className="flex items-center gap-1 text-caption font-medium text-fg-secondary">
              {field?.label}
              {field.required && (
                <span className="text-danger-fg" aria-hidden>
                  *
                </span>
              )}
            </span>
            <span className="flex items-center gap-1">
              <input
                type={inputType(field.type, field.key, secret)}
                value={fieldAsText(fieldValues[field.key])}
                placeholder={
                  field.placeholder ??
                  (secret && field.default === undefined ? '•••••••• (unchanged)' : '')
                }
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.key]: event.target.value }))
                }
                className="h-8 w-full rounded-md border border-border-default bg-sunken px-2 text-body text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
              />
              {secret && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => toggleReveal(field.key)}
                  aria-label={revealed.has(field.key) ? 'Hide secret' : 'Reveal secret'}
                >
                  {revealed.has(field.key) ? (
                    <EyeOff className="size-4" aria-hidden />
                  ) : (
                    <Eye className="size-4" aria-hidden />
                  )}
                </Button>
              )}
            </span>
            {secret && (
              <span className="text-micro text-fg-muted">
                Stored locally; never shown again after saving.
              </span>
            )}
          </label>
        );
      })}
      <div className="flex justify-end">
        <Button type="submit" variant="primary" size="sm">
          <Save className="size-4" aria-hidden />
          Save
        </Button>
      </div>
    </form>
  );
}
