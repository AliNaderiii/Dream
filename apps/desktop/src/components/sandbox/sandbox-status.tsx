/**
 * Sandbox status indicator — compact indicator for the status bar.
 */

import { Container, Loader2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';
import type { SandboxStatus } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

export function SandboxStatusIndicator() {
  const { call } = useBridge();
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const check = useCallback(async () => {
    setLoading(true);
    try {
      const result = await call<SandboxStatus>('sandbox.status');
      setStatus(result);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    void check();
    const interval = setInterval(check, 30_000); // Check every 30s
    return () => clearInterval(interval);
  }, [check]);

  if (loading && !status) {
    return (
      <span className="flex items-center gap-1 text-caption text-fg-muted">
        <Loader2 className="size-3 animate-spin" />
        <span>Sandbox…</span>
      </span>
    );
  }

  const available = status?.available === true;

  return (
    <span
      className={cn(
        'flex items-center gap-1 text-caption',
        available ? 'text-fg-muted' : 'text-fg-muted',
      )}
    >
      <Container className={cn('size-3', available && 'text-success-fg')} />
      <span>{available ? 'Sandbox' : 'No sandbox'}</span>
    </span>
  );
}