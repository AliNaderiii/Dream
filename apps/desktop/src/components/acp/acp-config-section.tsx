import { Bot, CheckCircle2, Plus, Radio, Server, ShieldCheck, Trash2 } from 'lucide-react';
import React, { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ACPAgentDto } from '@/lib/bridge/types';

interface ACPConfigSectionProps {
  agents: ACPAgentDto[];
  onAddAgent?: (agent: {
    name: string;
    endpoint: string;
    token?: string;
    description?: string;
  }) => void;
  onRemoveAgent?: (agentId: string) => void;
  onTestAgent?: (agentId: string) => Promise<void>;
}

export function ACPConfigSection({
  agents,
  onAddAgent,
  onRemoveAgent,
  onTestAgent,
}: ACPConfigSectionProps) {
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEndpoint, setNewEndpoint] = useState('');
  const [newToken, setNewToken] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [testingId, setTestingId] = useState<string | null>(null);

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      await onTestAgent?.(id);
    } finally {
      setTestingId(null);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newEndpoint.trim()) return;
    onAddAgent?.({
      name: newName.trim(),
      endpoint: newEndpoint.trim(),
      token: newToken.trim() || undefined,
      description: newDesc.trim(),
    });
    setNewName('');
    setNewEndpoint('');
    setNewToken('');
    setNewDesc('');
    setIsAddOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* 1. Inbound ACP Server */}
      <div className="rounded-xl border border-border-default bg-surface p-6 shadow-sm">
        <div className="flex items-center justify-between border-b border-border-default pb-4">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
              <Server className="size-5" />
            </div>
            <div>
              <h3 className="text-body font-semibold text-fg-primary">
                Inbound ACP Server (Drive Dream from External Editors)
              </h3>
              <p className="text-caption text-fg-secondary">
                Expose Dream's agent loop, tools, and sessions to VS Code, Cursor, and CLI tools via
                ACP.
              </p>
            </div>
          </div>
          <Badge variant="success" className="flex items-center gap-1">
            <CheckCircle2 className="size-3" /> Ready
          </Badge>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 text-caption">
          <div className="rounded-lg border border-border-default bg-surface-2 p-3 space-y-1">
            <span className="text-fg-muted font-medium">Protocol Version</span>
            <p className="font-mono text-fg-primary">Agent Client Protocol v1.0</p>
          </div>

          <div className="rounded-lg border border-border-default bg-surface-2 p-3 space-y-1">
            <span className="text-fg-muted font-medium">Authentication</span>
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-success-fg" />
              <span className="font-mono text-fg-primary">Bearer Token Protected</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Outbound External ACP Agents */}
      <div className="rounded-xl border border-border-default bg-surface p-6 shadow-sm">
        <div className="flex items-center justify-between pb-4">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-lg bg-info-bg text-info-fg">
              <Bot className="size-5" />
            </div>
            <div>
              <h3 className="text-body font-semibold text-fg-primary">
                Connected External ACP Agents
              </h3>
              <p className="text-caption text-fg-secondary">
                Drive other AI agents (Codex, Gemini CLI, Claude Code) from Dream panes and
                conversations.
              </p>
            </div>
          </div>
          <Button variant="primary" size="sm" onClick={() => setIsAddOpen(true)}>
            <Plus className="size-4" />
            Add External Agent
          </Button>
        </div>

        {/* Agents Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="rounded-lg border border-border-default bg-surface-2 p-4 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-fg-primary">{agent.name}</span>
                  <Badge variant="accent">ACP Agent</Badge>
                </div>
                <p className="mt-1 text-caption text-fg-secondary">{agent.description}</p>
                <p className="mt-2 font-mono text-micro text-fg-muted truncate">
                  Endpoint: {agent.endpoint}
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={testingId === agent.id}
                  onClick={() => void handleTest(agent.id)}
                >
                  <Radio className={`size-3.5 ${testingId === agent.id ? 'animate-spin' : ''}`} />
                  {testingId === agent.id ? 'Testing...' : 'Test Connection'}
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => onRemoveAgent?.(agent.id)}
                  className="text-danger-fg hover:bg-danger-bg"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Add Agent Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl border border-border-default bg-surface p-6 shadow-xl">
            <h3 className="text-h3 font-semibold text-fg-primary">Add External ACP Agent</h3>
            <form onSubmit={handleSubmit} className="mt-4 space-y-3 text-caption">
              <div>
                <label className="block font-medium text-fg-primary">Agent Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Claude Code"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 text-body text-fg-primary focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-medium text-fg-primary">Endpoint URL</label>
                <input
                  type="url"
                  required
                  placeholder="http://localhost:8001"
                  value={newEndpoint}
                  onChange={(e) => setNewEndpoint(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-body text-fg-primary focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-medium text-fg-primary">Bearer Token (optional)</label>
                <input
                  type="password"
                  placeholder="Secret token"
                  value={newToken}
                  onChange={(e) => setNewToken(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-caption text-fg-primary focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-medium text-fg-primary">Description</label>
                <input
                  type="text"
                  placeholder="Purpose of this external agent"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 text-caption text-fg-primary focus:border-accent focus:outline-none"
                />
              </div>

              <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-4">
                <Button type="button" variant="ghost" onClick={() => setIsAddOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Add Agent
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
