import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  LoaderCircle,
  Shield,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

import type { MessageToolCall } from '@/types';
import { cn } from '@/utils/cn';

const riskClass = {
  safe: 'bg-success-bg text-success-fg',
  guarded: 'bg-warning-bg text-warning-fg',
  dangerous: 'bg-danger-bg text-danger-fg',
};

export function ToolCallCard({ call }: { call: MessageToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const Status =
    call.status === 'running'
      ? LoaderCircle
      : call.status === 'ok'
        ? CheckCircle2
        : call.status === 'blocked'
          ? AlertTriangle
          : XCircle;
  return (
    <div
      className={cn(
        'my-2 overflow-hidden rounded-md border border-border-default bg-surface-2',
        call.status === 'running' && 'animate-pulse',
      )}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-start"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <Status
          className={cn(
            'size-4 shrink-0',
            call.status === 'ok'
              ? 'text-success-fg'
              : call.status === 'running'
                ? 'animate-spin text-accent-text'
                : 'text-danger-fg',
          )}
          aria-hidden
        />
        <code className="ltr-island min-w-0 flex-1 truncate text-code">
          <span className="text-fg-muted">[tool]</span> {call.name}(
          {Object.keys(call.arguments).join(', ')}) → {call.status}
        </code>
        <span
          className={cn(
            'flex items-center gap-1 rounded-full px-2 py-0.5 text-micro font-semibold',
            riskClass[call.risk],
          )}
        >
          <Shield className="size-3" />
          {call.risk}
        </span>
        <ChevronDown className={cn('size-4 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="border-t border-border-default p-3">
          <p className="mb-1 text-caption font-semibold text-fg-muted">Arguments</p>
          <pre className="ltr-island selectable overflow-x-auto whitespace-pre-wrap text-code">
            {JSON.stringify(call.arguments, null, 2)}
          </pre>
          {call.result && (
            <>
              <p className="mb-1 mt-3 text-caption font-semibold text-fg-muted">Result</p>
              <pre className="ltr-island selectable overflow-x-auto whitespace-pre-wrap text-code">
                {call.result}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
