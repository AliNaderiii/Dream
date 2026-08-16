import { Bot, Server, Settings as SettingsIcon } from 'lucide-react';
import { useEffect, useState } from 'react';

import { ACPConfigSection } from '@/components/acp/acp-config-section';
import { BrowserSettings } from '@/components/browser/browser-settings';
import { GatewaySettings } from '@/components/gateway/gateway-settings';
import { MCPServersList } from '@/components/mcp/mcp-servers-list';
import { SandboxSettings } from '@/components/sandbox/sandbox-settings';
import { Button } from '@/components/ui/button';
import { getBridgeClient } from '@/lib/bridge/client';
import type { ACPAgentDto, MCPServerDto, MCPToolDto } from '@/lib/bridge/types';
import { dialogApi, windowApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import type { Density, Locale, ThemeMode } from '@/types';

/** A labelled settings row. */
function Row({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-border-default py-3 last:border-b-0">
      <div className="min-w-0">
        <p className="text-body font-medium">{label}</p>
        {description && <p className="text-caption text-fg-secondary">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const THEMES: ThemeMode[] = ['light', 'dark', 'system'];
const DENSITIES: Density[] = ['comfortable', 'compact'];
const LOCALES: Array<{ value: Locale; label: string }> = [
  { value: 'en', label: 'English' },
  { value: 'fa', label: 'فارسی' },
];

export function SettingsRoute() {
  const [activeTab, setActiveTab] = useState<'general' | 'mcp' | 'acp'>('general');

  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const density = useAppStore((s) => s.density);
  const setDensity = useAppStore((s) => s.setDensity);
  const locale = useAppStore((s) => s.locale);
  const setLocale = useAppStore((s) => s.setLocale);
  const workspaceRoot = useAppStore((s) => s.workspaceRoot);
  const setWorkspaceRoot = useAppStore((s) => s.setWorkspaceRoot);

  const [minimizeToTray, setMinimizeToTray] = useState(false);
  const [closeToTray, setCloseToTray] = useState(true);

  // MCP & ACP State
  const [mcpServers, setMcpServers] = useState<MCPServerDto[]>([]);
  const [mcpTools, setMcpTools] = useState<MCPToolDto[]>([]);
  const [acpAgents, setAcpAgents] = useState<ACPAgentDto[]>([]);

  const client = getBridgeClient();

  const loadMcpAndAcp = async () => {
    try {
      const srvRes = await client.call<{ servers: MCPServerDto[] }>('mcp.list_servers', {});
      setMcpServers(srvRes.servers || []);

      const toolsRes = await client.call<{ tools: MCPToolDto[] }>('mcp.list_tools', {});
      setMcpTools(toolsRes.tools || []);

      const acpRes = await client.call<{ agents: ACPAgentDto[] }>('acp.client.list_agents', {});
      setAcpAgents(acpRes.agents || []);
    } catch {
      // fallback or ignore
    }
  };

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      try {
        const srvRes = await client.call<{ servers: MCPServerDto[] }>('mcp.list_servers', {});
        if (ignore) return;
        setMcpServers(srvRes.servers || []);

        const toolsRes = await client.call<{ tools: MCPToolDto[] }>('mcp.list_tools', {});
        if (ignore) return;
        setMcpTools(toolsRes.tools || []);

        const acpRes = await client.call<{ agents: ACPAgentDto[] }>('acp.client.list_agents', {});
        if (ignore) return;
        setAcpAgents(acpRes.agents || []);
      } catch {
        // fallback
      }
    };
    void run();
    return () => {
      ignore = true;
    };
  }, [client]);

  // Push window-behaviour preferences down to Rust whenever they change.
  useEffect(() => {
    void windowApi.setMinimizeToTray(minimizeToTray);
  }, [minimizeToTray]);

  useEffect(() => {
    void windowApi.setCloseToTray(closeToTray);
  }, [closeToTray]);

  const chooseWorkspace = async () => {
    const folder = await dialogApi.selectFolder({ title: 'Choose workspace folder' });
    if (!folder) return;
    await dialogApi.setWorkspaceRoot(folder);
    setWorkspaceRoot(folder);
  };

  // MCP handlers
  const handleAddMcpServer = async (data: {
    name: string;
    type: 'stdio' | 'sse' | 'ws';
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    url?: string;
  }) => {
    await client.call('mcp.add_server', data);
    await loadMcpAndAcp();
  };

  const handleRemoveMcpServer = async (serverId: string) => {
    await client.call('mcp.remove_server', { server_id: serverId });
    await loadMcpAndAcp();
  };

  const handleToggleMcpServer = async (serverId: string, enabled: boolean) => {
    await client.call('mcp.toggle_server', { server_id: serverId, enabled });
    await loadMcpAndAcp();
  };

  const handleToggleMcpTool = async (serverId: string, toolName: string, enabled: boolean) => {
    await client.call('mcp.toggle_tool', { server_id: serverId, tool_name: toolName, enabled });
    await loadMcpAndAcp();
  };

  const handleTestMcpConnection = async (serverId: string) => {
    await client.call('mcp.test_connection', { server_id: serverId });
    await loadMcpAndAcp();
  };

  // ACP handlers
  const handleAddAcpAgent = async (agent: {
    name: string;
    endpoint: string;
    token?: string;
    description?: string;
  }) => {
    await client.call('acp.client.add_agent', agent);
    await loadMcpAndAcp();
  };

  const handleRemoveAcpAgent = async (agentId: string) => {
    await client.call('acp.client.remove_agent', { agent_id: agentId });
    await loadMcpAndAcp();
  };

  const handleTestAcpAgent = async (agentId: string) => {
    await client.call('acp.client.test_agent', { agent_id: agentId });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface-2 p-6">
      {/* Top Header & Tabs */}
      <div className="flex items-center justify-between border-b border-border-default pb-4">
        <div>
          <h1 className="text-h2 font-semibold text-fg-primary flex items-center gap-2">
            <SettingsIcon className="size-6 text-accent" />
            Settings & Integrations
          </h1>
          <p className="text-caption text-fg-secondary">
            Configure system appearance, MCP server extensions, and ACP agent connections.
          </p>
        </div>

        <div className="flex rounded-lg border border-border-default bg-surface p-1">
          <button
            type="button"
            onClick={() => setActiveTab('general')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'general'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <SettingsIcon className="size-4" />
            General
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('mcp')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'mcp'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <Server className="size-4" />
            MCP Servers ({mcpServers.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('acp')}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-caption font-medium transition-all ${
              activeTab === 'acp'
                ? 'bg-accent text-fg-inverse shadow-xs'
                : 'text-fg-secondary hover:text-fg-primary'
            }`}
          >
            <Bot className="size-4" />
            ACP Interoperability ({acpAgents.length})
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      <div className="mt-6 flex-1 overflow-y-auto">
        {activeTab === 'general' && (
          <div className="mx-auto max-w-2xl space-y-8 rounded-xl border border-border-default bg-surface p-6 shadow-sm">
            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">Appearance</h2>

              <Row label="Theme" description="Follows your system setting unless overridden.">
                <div className="flex gap-1">
                  {THEMES.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={theme === option ? 'primary' : 'secondary'}
                      onClick={() => setTheme(option)}
                    >
                      {option}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row label="Density" description="Compact reduces component padding by 25%.">
                <div className="flex gap-1">
                  {DENSITIES.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={density === option ? 'primary' : 'secondary'}
                      onClick={() => setDensity(option)}
                    >
                      {option}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row
                label="Language"
                description="Persian switches the whole shell to right-to-left."
              >
                <div className="flex gap-1">
                  {LOCALES.map((option) => (
                    <Button
                      key={option.value}
                      size="sm"
                      variant={locale === option.value ? 'primary' : 'secondary'}
                      onClick={() => setLocale(option.value)}
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </Row>
            </section>

            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">Window</h2>

              <Row label="Minimize to tray" description="Hide the window instead of minimizing it.">
                <Button
                  size="sm"
                  variant={minimizeToTray ? 'primary' : 'secondary'}
                  aria-pressed={minimizeToTray}
                  onClick={() => setMinimizeToTray((v) => !v)}
                >
                  {minimizeToTray ? 'On' : 'Off'}
                </Button>
              </Row>

              <Row
                label="Close to tray"
                description="Keep Dream running in the tray when the window closes."
              >
                <Button
                  size="sm"
                  variant={closeToTray ? 'primary' : 'secondary'}
                  aria-pressed={closeToTray}
                  onClick={() => setCloseToTray((v) => !v)}
                >
                  {closeToTray ? 'On' : 'Off'}
                </Button>
              </Row>
            </section>

            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">Workspace</h2>

              <Row
                label="Workspace folder"
                description={workspaceRoot ?? 'No folder selected — file access is unrestricted.'}
              >
                <Button size="sm" onClick={() => void chooseWorkspace()}>
                  Choose…
                </Button>
              </Row>
            </section>

            {/* P-08: Docker sandbox */}
            <SandboxSettings />

            {/* P-08: Browser control */}
            <BrowserSettings />

            {/* P-08: Web gateway */}
            <GatewaySettings />
          </div>
        )}

        {activeTab === 'mcp' && (
          <div className="mx-auto max-w-4xl">
            <MCPServersList
              servers={mcpServers}
              tools={mcpTools}
              onAddServer={(data) => void handleAddMcpServer(data)}
              onRemoveServer={(id) => void handleRemoveMcpServer(id)}
              onToggleServer={(id, enabled) => void handleToggleMcpServer(id, enabled)}
              onToggleTool={(sId, tName, en) => void handleToggleMcpTool(sId, tName, en)}
              onTestConnection={handleTestMcpConnection}
            />
          </div>
        )}

        {activeTab === 'acp' && (
          <div className="mx-auto max-w-4xl">
            <ACPConfigSection
              agents={acpAgents}
              onAddAgent={(a) => void handleAddAcpAgent(a)}
              onRemoveAgent={(id) => void handleRemoveAcpAgent(id)}
              onTestAgent={handleTestAcpAgent}
            />
          </div>
        )}
      </div>
    </div>
  );
}
