/**
 * Sandbox status indicator — compact indicator for the status bar.
 */

import { Container, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';
import type { SandboxStatus } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

export function SandboxStatusIndicator() {
  const { call } = useBridge();
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      setLoading(true);
      try {
        const result = await call<SandboxStatus>('sandbox.status');
        if (!ignore) setStatus(result);
      } catch {
        if (!ignore) setStatus(null);
      } finally {
        if (!ignore) setLoading(false);
      }
    };
    void run();
    const interval = setInterval(() => {
      void run();
    }, 30_000);
    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, [call]);

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
