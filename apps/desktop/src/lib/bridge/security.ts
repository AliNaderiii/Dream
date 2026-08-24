/**
 * Security engine status (SEC Stage B).
 *
 * Reads `security.status` from the kernel once the bridge is ready. The
 * surface is fail-safe: any error (older kernel without the method,
 * disconnected bridge) yields `null`, and every indicator stays hidden —
 * a missing answer must never look like "approvals are on".
 */

import { useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';

/** Wire shape returned by the kernel's `security.status`. */
export interface SecurityStatus {
  mode: 'smart' | 'manual' | 'off';
  cron_mode: 'deny' | 'auto';
  single_query_mode: 'deny' | 'auto';
  /** True only in `off` mode — the state that needs persistent warnings. */
  off_active: boolean;
  /** The L3 floor state; it is always "always-on" and never configurable. */
  floor: string;
  history_path: string | null;
  history_available: boolean;
}

/**
 * The live engine status, or `null` while unknown/unavailable. Re-fetches
 * whenever the connection becomes ready again.
 */
export function useSecurityStatus(): SecurityStatus | null {
  const { call, state } = useBridge();
  const [status, setStatus] = useState<SecurityStatus | null>(null);

  useEffect(() => {
    if (state !== 'ready') return;
    let cancelled = false;
    call<SecurityStatus>('security.status')
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [call, state]);

  return status;
}
