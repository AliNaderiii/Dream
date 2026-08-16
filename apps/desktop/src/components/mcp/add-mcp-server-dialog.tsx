import { Globe, Plus, Server, Terminal, X } from 'lucide-react';
import React, { useState } from 'react';

import { Button } from '@/components/ui/button';

interface AddMCPServerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onAddServer: (serverData: {
    name: string;
    type: 'stdio' | 'sse' | 'ws';
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    url?: string;
    headers?: Record<string, string>;
  }) => void;
}

export function AddMCPServerDialog({ isOpen, onClose, onAddServer }: AddMCPServerDialogProps) {
  const [name, setName] = useState('');
  const [type, setType] = useState<'stdio' | 'sse' | 'ws'>('stdio');
  const [command, setCommand] = useState('');
  const [argsStr, setArgsStr] = useState('');
  const [url, setUrl] = useState('');
  const [envJson, setEnvJson] = useState('{}');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    let parsedEnv: Record<string, string> = {};
    try {
      if (envJson.trim()) parsedEnv = JSON.parse(envJson) as Record<string, string>;
    } catch {
      // ignore or default
    }

    const args = argsStr
      .trim()
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    onAddServer({
      name: name.trim(),
      type,
      command: type === 'stdio' ? command.trim() : undefined,
      args: type === 'stdio' ? args : undefined,
      env: type === 'stdio' ? parsedEnv : undefined,
      url: type !== 'stdio' ? url.trim() : undefined,
    });

    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="w-full max-w-lg rounded-xl border border-border-default bg-surface p-6 shadow-xl animate-in fade-in zoom-in-95 duration-fast">
        <div className="flex items-center justify-between border-b border-border-default pb-3">
          <div className="flex items-center gap-2">
            <Server className="size-5 text-accent" />
            <h3 className="text-h3 font-semibold text-fg-primary">Add MCP Server</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-fg-muted hover:bg-surface-2 hover:text-fg-primary"
          >
            <X className="size-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-caption">
          {/* Server Name */}
          <div>
            <label className="block font-medium text-fg-primary">Server Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Local SQLite MCP"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 text-body text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
            />
          </div>

          {/* Transport Type */}
          <div>
            <label className="block font-medium text-fg-primary">Transport Type</label>
            <div className="mt-1 grid grid-cols-3 gap-2">
              {(['stdio', 'sse', 'ws'] as const).map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setType(t)}
                  className={`flex items-center justify-center gap-1.5 rounded-md border py-2 font-medium capitalize transition-all ${
                    type === t
                      ? 'border-accent bg-accent-soft/30 text-accent-text font-semibold'
                      : 'border-border-default bg-surface-2 text-fg-secondary hover:bg-surface-3'
                  }`}
                >
                  {t === 'stdio' ? <Terminal className="size-4" /> : <Globe className="size-4" />}
                  {t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Type-Specific Fields */}
          {type === 'stdio' ? (
            <>
              <div>
                <label className="block font-medium text-fg-primary">Command</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. npx, python, uvx"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-body text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-medium text-fg-primary">
                  Arguments (one per line)
                </label>
                <textarea
                  rows={2}
                  placeholder="-y&#10;@modelcontextprotocol/server-filesystem"
                  value={argsStr}
                  onChange={(e) => setArgsStr(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-caption text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-medium text-fg-primary">
                  Environment Variables (JSON)
                </label>
                <input
                  type="text"
                  placeholder='{"DEBUG": "1"}'
                  value={envJson}
                  onChange={(e) => setEnvJson(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-caption text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
                />
              </div>
            </>
          ) : (
            <div>
              <label className="block font-medium text-fg-primary">
                Remote Server Endpoint URL
              </label>
              <input
                type="url"
                required
                placeholder="http://localhost:8000/sse"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="mt-1 w-full rounded-md border border-border-default bg-surface-2 px-3 py-1.5 font-mono text-body text-fg-primary placeholder:text-fg-muted focus:border-accent focus:outline-none"
              />
            </div>
          )}

          {/* Footer Actions */}
          <div className="mt-6 flex justify-end gap-2 border-t border-border-default pt-4">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              <Plus className="size-4" />
              Add Server
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
