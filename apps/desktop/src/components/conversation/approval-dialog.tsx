import * as Dialog from '@radix-ui/react-dialog';
import { AlertTriangle, ShieldAlert, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';

interface Approval {
  approval_id: string;
  name: string;
  arguments: Record<string, unknown>;
  risk: string;
  summary: string;
  created_at: number;
  expires_at: number;
}

export function ApprovalDialog() {
  const { call, state } = useBridge();
  const [queue, setQueue] = useState<Approval[]>([]);
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (state !== 'ready') return;
    const refresh = () =>
      void call<{ approvals: Approval[] }>('approval.list')
        .then((result) => setQueue(result.approvals))
        .catch(() => undefined);
    refresh();
    const timer = window.setInterval(() => {
      setNow(Date.now() / 1_000);
      refresh();
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [call, state]);
  const current = queue[0];
  if (!current) return null;
  const remaining = Math.max(0, Math.ceil(current.expires_at - now));
  const resolve = (decision: 'allow' | 'deny' | 'always_allow') => {
    setQueue((items) => items.slice(1));
    void call('approval.resolve', { approval_id: current.approval_id, decision }).catch(
      () => undefined,
    );
  };
  return (
    <Dialog.Root open modal>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm" />
        <Dialog.Content
          aria-describedby="approval-description"
          className="fixed start-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-danger-fg/30 bg-surface-raised p-5 shadow-e3 rtl:translate-x-1/2"
        >
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-danger-bg p-2 text-danger-fg">
              <ShieldAlert className="size-6" />
            </div>
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-h2 font-semibold">Approval required</Dialog.Title>
              <p className="mt-0.5 text-caption text-fg-muted">
                تأیید شما لازم است · {queue.length} pending
              </p>
            </div>
            <button type="button" onClick={() => resolve('deny')} aria-label="Deny and close">
              <X className="size-5 text-fg-muted" />
            </button>
          </div>
          <div
            id="approval-description"
            className="mt-4 rounded-lg border border-border-default bg-sunken p-3"
          >
            <div className="mb-2 flex items-center justify-between">
              <code className="ltr-island font-semibold">{current.name}</code>
              <span className="rounded-full bg-danger-bg px-2 py-0.5 text-caption font-semibold text-danger-fg">
                {current.risk}
              </span>
            </div>
            <p className="break-words text-body text-fg-secondary">{current.summary}</p>
            <details className="mt-2">
              <summary className="cursor-pointer text-caption text-fg-muted">
                Full arguments
              </summary>
              <pre className="ltr-island selectable mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-code">
                {JSON.stringify(current.arguments, null, 2)}
              </pre>
            </details>
          </div>
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-caption">
              <span className="flex items-center gap-1 text-warning-fg">
                <AlertTriangle className="size-3.5" />
                Auto-deny in {remaining}s
              </span>
              <span>{Math.round((remaining / 60) * 100)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
              <div
                className="h-full bg-warning-fg transition-[width] duration-1000"
                style={{ width: `${(remaining / 60) * 100}%` }}
              />
            </div>
          </div>
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => resolve('deny')}
              className="rounded-md border border-border-strong px-3 py-2 font-medium hover:bg-surface-2"
            >
              Deny
            </button>
            <button
              type="button"
              onClick={() => resolve('always_allow')}
              className="rounded-md border border-warning-fg/40 bg-warning-bg px-3 py-2 font-medium text-warning-fg"
            >
              Always allow {current.name}
            </button>
            <button
              type="button"
              autoFocus
              onClick={() => resolve('allow')}
              className="rounded-md bg-accent px-4 py-2 font-medium text-fg-inverse"
            >
              Allow once
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
