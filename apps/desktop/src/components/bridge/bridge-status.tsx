/**
 * Bridge connection UI: a status-bar indicator and a transient error toast.
 *
 * Both read from `useBridge()`. The indicator shows the live connection state
 * (ready / connecting / reconnecting / disconnected) and an "Echo" badge when
 * running on the in-memory fallback; clicking it while disconnected nudges a
 * reconnect. The toast surfaces the last RPC error with its taxonomy code.
 */

import { AlertTriangle, PlugZap, X } from 'lucide-react';
import { useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';
import { RPC_ERROR_LABEL } from '@/lib/bridge/types';
import type { BridgeConnectionState } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';

const STATE_META: Record<BridgeConnectionState, { label: string; dot: string; text: string }> = {
  connecting: { label: 'Connecting', dot: 'bg-warning-fg', text: 'text-warning-fg' },
  ready: { label: 'Connected', dot: 'bg-success-fg', text: 'text-fg-muted' },
  reconnecting: { label: 'Reconnecting', dot: 'bg-warning-fg', text: 'text-warning-fg' },
  disconnected: { label: 'Disconnected', dot: 'bg-danger-fg', text: 'text-danger-fg' },
};

/** A compact connection-state readout for the status bar. */
export function BridgeStatusIndicator() {
  const { state, isFallback, reconnect } = useBridge();
  const meta = STATE_META[state];
  const interactive = state === 'disconnected';

  return (
    <button
      type="button"
      onClick={interactive ? reconnect : undefined}
      disabled={!interactive}
      title={
        interactive
          ? 'Bridge disconnected — click to reconnect'
          : `Bridge ${meta?.label.toLowerCase()}`
      }
      className="flex items-center gap-1.5 rounded-xs hover:text-fg-primary disabled:cursor-default disabled:hover:text-fg-secondary"
      aria-label={`Bridge ${meta?.label}`}
    >
      <span
        className={cn('size-2 rounded-full', meta.dot, state === 'connecting' && 'animate-pulse')}
        aria-hidden
      />
      <span className={meta.text}>{meta?.label}</span>
      {isFallback && (
        <span className="rounded-xs bg-surface-raised px-1 text-caption text-fg-muted">Echo</span>
      )}
    </button>
  );
}

/** A dismissible toast for the most recent bridge error. */
export function BridgeErrorToast() {
  const { lastError } = useBridge();
  const [dismissedCode, setDismissedCode] = useState<number | null>(null);

  if (!lastError || lastError.code === dismissedCode) return null;

  const label = RPC_ERROR_LABEL[lastError.code] ?? 'Error';

  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-border-default bg-surface-raised p-3 text-body text-fg-primary shadow-md"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger-fg" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {label} <span className="ltr-island text-fg-muted">({lastError.code})</span>
        </p>
        <p className="mt-0.5 break-words text-fg-secondary">{lastError.message}</p>
        {lastError.isApprovalRequired && (
          <p className="mt-1 flex items-center gap-1 text-fg-muted">
            <PlugZap className="size-3" aria-hidden /> Approval required — resolve it to continue.
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={() => setDismissedCode(lastError.code)}
        aria-label="Dismiss error"
        className="shrink-0 rounded-xs text-fg-muted hover:text-fg-primary"
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}
