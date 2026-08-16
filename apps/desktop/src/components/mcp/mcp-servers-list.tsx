import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Globe,
  Plus,
  Radio,
  Server,
  Terminal,
  Trash2,
  Wrench,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { MCPServerDto, MCPToolDto } from '@/lib/bridge/types';

import { AddMCPServerDialog } from './add-mcp-server-dialog';
import { MCPToolsList } from './mcp-tools-list';

interface MCPServersListProps {
  servers: MCPServerDto[];
  tools?: MCPToolDto[];
  onAddServer: (serverData: {
    name: string;
    type: 'stdio' | 'sse' | 'ws';
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    url?: string;
  }) => void;
  onRemoveServer: (serverId: string) => void;
  onToggleServer: (serverId: string, enabled: boolean) => void;
  onToggleTool?: (serverId: string, toolName: string, enabled: boolean) => void;
  onTestConnection?: (serverId: string) => Promise<void>;
}

export function MCPServersList({
  servers,
  tools = [],
  onAddServer,
  onRemoveServer,
  onToggleServer,
  onToggleTool,
  onTestConnection,
}: MCPServersListProps) {
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [expandedServerIds, setExpandedServerIds] = useState<Set<string>>(new Set());
  const [testingId, setTestingId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedServerIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      await onTestConnection?.(id);
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-body font-semibold text-fg-primary flex items-center gap-2">
            <Server className="size-4 text-accent" />
            Model Context Protocol (MCP) Servers
          </h3>
          <p className="text-caption text-fg-secondary">
            Connect external tool providers, filesystems, and databases via MCP.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setIsAddOpen(true)}>
          <Plus className="size-4" />
          Add MCP Server
        </Button>
      </div>

      {servers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-default bg-surface-2 p-8 text-center text-fg-secondary">
          <Server className="mx-auto mb-2 size-8 opacity-40" />
          <p className="text-body font-medium">No MCP Servers Configured</p>
          <p className="mt-1 text-caption text-fg-muted">
            Add a stdio process or remote SSE/WebSocket server to extend Dream's tools.
          </p>
          <Button variant="secondary" size="sm" className="mt-4" onClick={() => setIsAddOpen(true)}>
            <Plus className="size-4" />
            Add Server
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {servers.map((server) => {
            const isExpanded = expandedServerIds.has(server.id);
            const serverTools = tools.filter((t) => t.server_id === server.id);

            return (
              <div
                key={server.id}
                className="rounded-xl border border-border-default bg-surface p-4 shadow-xs transition-colors hover:border-border-hover"
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => toggleExpand(server.id)}
                      className="rounded p-1 text-fg-muted hover:bg-surface-2 hover:text-fg-primary"
                    >
                      {isExpanded ? (
                        <ChevronDown className="size-4" />
                      ) : (
                        <ChevronRight className="size-4" />
                      )}
                    </button>

                    <div className="flex size-8 items-center justify-center rounded-md bg-accent-soft text-accent">
                      {server.type === 'stdio' ? (
                        <Terminal className="size-4" />
                      ) : (
                        <Globe className="size-4" />
                      )}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-fg-primary">{server.name}</span>
                        <Badge variant="neutral">{server.type.toUpperCase()}</Badge>
                        <Badge
                          variant={server.enabled ? 'success' : 'neutral'}
                          className="flex items-center gap-1"
                        >
                          {server.enabled ? (
                            <CheckCircle2 className="size-3" />
                          ) : (
                            <XCircle className="size-3" />
                          )}
                          {server.enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                      </div>

                      <p className="mt-0.5 font-mono text-micro text-fg-muted">
                        {server.command
                          ? `${server.command} ${server.args?.join(' ') || ''}`
                          : server.url}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={testingId === server.id}
                      onClick={() => void handleTest(server.id)}
                    >
                      <Radio
                        className={`size-3.5 ${testingId === server.id ? 'animate-spin' : ''}`}
                      />
                      {testingId === server.id ? 'Testing...' : 'Test'}
                    </Button>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={server.enabled}
                      onClick={() => onToggleServer(server.id, !server.enabled)}
                      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-fast ease-standard focus-visible:outline-none ${
                        server.enabled ? 'bg-accent' : 'bg-surface-3'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block size-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-fast ease-standard ${
                          server.enabled ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>

                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => onRemoveServer(server.id)}
                      className="text-danger-fg hover:bg-danger-bg hover:text-danger-fg"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>

                {/* Expandable Tools view */}
                {isExpanded && (
                  <div className="mt-4 border-t border-border-default pt-4">
                    <div className="mb-2 flex items-center justify-between">
                      <h4 className="text-caption font-semibold text-fg-primary flex items-center gap-1.5">
                        <Wrench className="size-3.5 text-accent" />
                        Discovered Tools ({serverTools.length})
                      </h4>
                    </div>
                    <MCPToolsList tools={serverTools} onToggleTool={onToggleTool} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <AddMCPServerDialog
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        onAddServer={onAddServer}
      />
    </div>
  );
}
