import {
  ChevronDown,
  ChevronRight,
  Code2,
  Cpu,
  FileText,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Wrench,
} from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import type { ProvenanceRecordDto } from '@/lib/bridge/types';

interface ProvenanceTimelineProps {
  records: ProvenanceRecordDto[];
  onSelectRecord?: (record: ProvenanceRecordDto) => void;
  selectedRecordId?: string | null;
}

export function ProvenanceTimeline({
  records,
  onSelectRecord,
  selectedRecordId,
}: ProvenanceTimelineProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case 'tool_call':
        return (
          <Badge variant="accent" className="flex items-center gap-1">
            <Wrench className="size-3" /> Tool Call
          </Badge>
        );
      case 'code_execution':
        return (
          <Badge variant="info" className="flex items-center gap-1">
            <Code2 className="size-3" /> Code Exec
          </Badge>
        );
      case 'file_write':
      case 'file_read':
        return (
          <Badge variant="warning" className="flex items-center gap-1">
            <FileText className="size-3" /> File I/O
          </Badge>
        );
      case 'model_response':
        return (
          <Badge variant="success" className="flex items-center gap-1">
            <Cpu className="size-3" /> Model Response
          </Badge>
        );
      case 'user_message':
      case 'agent_message':
        return (
          <Badge variant="neutral" className="flex items-center gap-1">
            <MessageSquare className="size-3" /> Message
          </Badge>
        );
      case 'approval_granted':
        return (
          <Badge variant="success" className="flex items-center gap-1">
            <ShieldCheck className="size-3" /> Approved
          </Badge>
        );
      case 'approval_denied':
        return (
          <Badge variant="danger" className="flex items-center gap-1">
            <ShieldAlert className="size-3" /> Denied
          </Badge>
        );
      default:
        return (
          <Badge variant="neutral" className="flex items-center gap-1">
            <Terminal className="size-3" /> {type}
          </Badge>
        );
    }
  };

  if (records.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-fg-secondary">
        <Terminal className="mb-2 size-8 opacity-40" />
        <p className="text-body font-medium">No provenance records found</p>
        <p className="text-caption text-fg-muted">
          Events will be recorded automatically during conversations and tool runs.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {records.map((rec, index) => {
        const isExpanded = expandedIds.has(rec.record_id);
        const isSelected = selectedRecordId === rec.record_id;
        const toolName = (rec.payload['tool_name'] as string) || (rec.payload['tool'] as string);
        const command = (rec.payload['command'] as string) || '';
        const msg = (rec.payload['message'] as string) || (rec.payload['reply'] as string);

        return (
          <div
            key={rec.record_id}
            onClick={() => onSelectRecord?.(rec)}
            className={`cursor-pointer rounded-lg border transition-all duration-fast ${
              isSelected
                ? 'border-accent bg-accent-soft/20 shadow-sm'
                : 'border-border-default bg-surface hover:border-border-hover hover:bg-surface-2'
            } p-3`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={(e) => toggleExpand(rec.record_id, e)}
                  className="rounded p-0.5 text-fg-muted hover:bg-surface-3 hover:text-fg-primary"
                >
                  {isExpanded ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </button>
                {getEventBadge(rec.event_type)}
                <span className="font-mono text-caption text-fg-secondary">
                  #{records.length - index}
                </span>
                <span className="truncate text-body font-medium text-fg-primary">
                  {toolName
                    ? `Tool: ${toolName}`
                    : command
                      ? `Exec: ${command}`
                      : msg
                        ? msg.slice(0, 50)
                        : rec.record_id.slice(0, 12)}
                </span>
              </div>

              <div className="flex items-center gap-3 text-caption text-fg-muted">
                {rec.duration_ms !== undefined && rec.duration_ms !== null && (
                  <span className="font-mono">{rec.duration_ms}ms</span>
                )}
                {rec.token_count && <span className="font-mono">{rec.token_count} tok</span>}
                <span className="font-mono text-micro">
                  {new Date(rec.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </span>
              </div>
            </div>

            {/* Expanded details */}
            {isExpanded && (
              <div className="mt-3 space-y-2 border-t border-border-default pt-3 text-caption">
                <div className="grid grid-cols-2 gap-2 text-fg-secondary">
                  <div>
                    <span className="font-semibold text-fg-primary">Record ID:</span>{' '}
                    <span className="font-mono text-micro">{rec.record_id}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-fg-primary">Agent / Session:</span>{' '}
                    <span className="font-mono text-micro">{rec.agent_id}</span>
                  </div>
                  {rec.parent_record_id && (
                    <div>
                      <span className="font-semibold text-fg-primary">Parent:</span>{' '}
                      <span className="font-mono text-micro">{rec.parent_record_id}</span>
                    </div>
                  )}
                  {rec.model_snapshot && (
                    <div>
                      <span className="font-semibold text-fg-primary">Model:</span>{' '}
                      <span>{rec.model_snapshot.model || rec.model_snapshot.provider}</span>
                    </div>
                  )}
                  <div className="col-span-2">
                    <span className="font-semibold text-fg-primary">SHA-256 Hash:</span>{' '}
                    <span className="break-all font-mono text-micro text-fg-muted">{rec.hash}</span>
                  </div>
                </div>

                {/* Payload */}
                {Object.keys(rec.payload).length > 0 && (
                  <div className="mt-2">
                    <p className="font-semibold text-fg-primary">Payload:</p>
                    <pre className="mt-1 max-h-36 overflow-auto rounded bg-surface-2 p-2 font-mono text-micro text-fg-secondary">
                      {JSON.stringify(rec.payload, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Input / Output Snapshots */}
                {(rec.input_snapshot.length > 0 || rec.output_snapshot.length > 0) && (
                  <div className="mt-2 flex gap-4">
                    {rec.input_snapshot.length > 0 && (
                      <div className="flex-1">
                        <p className="font-semibold text-fg-primary">
                          Inputs ({rec.input_snapshot.length}):
                        </p>
                        <ul className="mt-1 list-disc space-y-1 ps-4 font-mono text-micro text-fg-secondary">
                          {rec.input_snapshot.map((f, i) => (
                            <li key={i}>
                              {f.path} ({f.size} bytes)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {rec.output_snapshot.length > 0 && (
                      <div className="flex-1">
                        <p className="font-semibold text-fg-primary">
                          Outputs ({rec.output_snapshot.length}):
                        </p>
                        <ul className="mt-1 list-disc space-y-1 ps-4 font-mono text-micro text-fg-secondary">
                          {rec.output_snapshot.map((f, i) => (
                            <li key={i}>
                              {f.path} ({f.size} bytes)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
