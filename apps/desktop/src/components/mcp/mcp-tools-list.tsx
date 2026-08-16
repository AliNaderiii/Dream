import { ChevronDown, ChevronRight, Wrench } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import type { MCPToolDto } from '@/lib/bridge/types';

interface MCPToolsListProps {
  tools: MCPToolDto[];
  onToggleTool?: (serverId: string, toolName: string, enabled: boolean) => void;
}

export function MCPToolsList({ tools, onToggleTool }: MCPToolsListProps) {
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

  const toggleExpand = (toolName: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
  };

  if (tools.length === 0) {
    return (
      <div className="flex h-32 flex-col items-center justify-center text-caption text-fg-muted">
        <Wrench className="mb-1 size-5 opacity-40" />
        <p>No MCP tools discovered on this server.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tools.map((tool) => {
        const isExpanded = expandedTools.has(tool.name);
        return (
          <div
            key={`${tool.server_id}_${tool.name}`}
            className="rounded-lg border border-border-default bg-surface p-3 transition-colors hover:border-border-hover"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleExpand(tool.name)}
                  className="rounded p-0.5 text-fg-muted hover:bg-surface-2 hover:text-fg-primary"
                >
                  {isExpanded ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </button>
                <span className="font-mono text-body-sm font-semibold text-fg-primary">
                  {tool.name}
                </span>
                <Badge
                  variant={
                    tool.risk === 'safe'
                      ? 'success'
                      : tool.risk === 'dangerous'
                        ? 'danger'
                        : 'accent'
                  }
                >
                  {tool.risk}
                </Badge>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={tool.enabled}
                  onClick={() => onToggleTool?.(tool.server_id, tool.name, !tool.enabled)}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-fast ease-standard focus-visible:outline-none ${
                    tool.enabled ? 'bg-accent' : 'bg-surface-3'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block size-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-fast ease-standard ${
                      tool.enabled ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            </div>

            {tool.description && (
              <p className="mt-1 ps-6 text-caption text-fg-secondary">{tool.description}</p>
            )}

            {isExpanded && (
              <div className="mt-3 ps-6">
                <p className="text-micro font-semibold text-fg-muted uppercase tracking-wider">
                  Input JSON Schema:
                </p>
                <pre className="mt-1 max-h-36 overflow-auto rounded bg-surface-2 p-2 font-mono text-micro text-fg-secondary">
                  {JSON.stringify(tool.input_schema, null, 2)}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
