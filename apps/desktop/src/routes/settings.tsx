import { Bot, Server, Settings as SettingsIcon } from 'lucide-react';
import { useEffect, useState } from 'react';

import { ACPConfigSection } from '@/components/acp/acp-config-section';
import { BillingSummary } from '@/components/billing/billing-summary';
import { BrowserSettings } from '@/components/browser/browser-settings';
import { GatewaySettings } from '@/components/gateway/gateway-settings';
import { MCPServersList } from '@/components/mcp/mcp-servers-list';
import { SandboxSettings } from '@/components/sandbox/sandbox-settings';
import { Button } from '@/components/ui/button';
import { LANGUAGES, useTranslation } from '@/lib/i18n';
import { getBridgeClient } from '@/lib/bridge/client';
import type { ACPAgentDto, MCPServerDto, MCPToolDto } from '@/lib/bridge/types';
import { dialogApi, windowApi } from '@/lib/tauri';
import { MAX_UI_ZOOM, MIN_UI_ZOOM, useAppStore } from '@/stores/use-app-store';
import type { Accent, Density, NumeralStyle, ThemeMode } from '@/types';

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

const THEMES: ThemeMode[] = ['light', 'warm', 'dark', 'system'];
const ACCENTS: Accent[] = ['violet', 'ocean', 'forest', 'ember'];
const DENSITIES: Density[] = ['comfortable', 'dense'];
const NUMERAL_STYLES: NumeralStyle[] = ['latin', 'persian'];

export function SettingsRoute() {
  const { t } = useTranslation('settings');
  const { t: tc } = useTranslation('common');
  const [activeTab, setActiveTab] = useState<'general' | 'mcp' | 'acp'>('general');

  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const density = useAppStore((s) => s.density);
  const setDensity = useAppStore((s) => s.setDensity);
  const accent = useAppStore((s) => s.accent);
  const setAccent = useAppStore((s) => s.setAccent);
  const zoom = useAppStore((s) => s.zoom);
  const setZoom = useAppStore((s) => s.setZoom);
  const reduceMotion = useAppStore((s) => s.reduceMotion);
  const setReduceMotion = useAppStore((s) => s.setReduceMotion);
  const numerals = useAppStore((s) => s.numerals);
  const setNumerals = useAppStore((s) => s.setNumerals);
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
    const folder = await dialogApi.selectFolder({ title: tc('topbar.chooseWorkspace') });
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
            {t('title')}
          </h1>
          <p className="text-caption text-fg-secondary">{t('subtitle')}</p>
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
            {t('tabs.general')}
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
            {t('tabs.mcp')} ({mcpServers.length})
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
            {t('tabs.acp')} ({acpAgents.length})
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      <div className="mt-6 flex-1 overflow-y-auto">
        {activeTab === 'general' && (
          <div className="mx-auto max-w-2xl space-y-8 rounded-xl border border-border-default bg-surface p-6 shadow-sm">
            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">{t('appearance')}</h2>

              <Row label={t('theme')} description={t('themeDesc')}>
                <div className="flex flex-wrap justify-end gap-1">
                  {THEMES.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={theme === option ? 'primary' : 'secondary'}
                      aria-pressed={theme === option}
                      onClick={() => setTheme(option)}
                    >
                      {t(`themeOptions.${option}`)}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row label={t('accent')} description={t('accentDesc')}>
                <div className="flex flex-wrap justify-end gap-1">
                  {ACCENTS.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={accent === option ? 'primary' : 'secondary'}
                      aria-pressed={accent === option}
                      onClick={() => setAccent(option)}
                    >
                      {t(`accentOptions.${option}`)}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row label={t('density')} description={t('densityDesc')}>
                <div className="flex gap-1">
                  {DENSITIES.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={density === option ? 'primary' : 'secondary'}
                      aria-pressed={density === option}
                      onClick={() => setDensity(option)}
                    >
                      {t(`densityOptions.${option}`)}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row label={t('zoom')} description={t('zoomDesc')}>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min={MIN_UI_ZOOM}
                    max={MAX_UI_ZOOM}
                    step={5}
                    value={zoom}
                    aria-label={t('zoom')}
                    onChange={(event) => setZoom(Number(event.target.value))}
                    className="w-28 accent-accent"
                  />
                  <output className="ltr-island tabular w-10 text-end text-caption">{zoom}%</output>
                </div>
              </Row>

              <Row label={t('reduceMotion')} description={t('reduceMotionDesc')}>
                <Button
                  size="sm"
                  variant={reduceMotion ? 'primary' : 'secondary'}
                  aria-pressed={reduceMotion}
                  onClick={() => setReduceMotion(!reduceMotion)}
                >
                  {reduceMotion ? tc('generic.on') : tc('generic.off')}
                </Button>
              </Row>

              <Row label={t('numerals')} description={t('numeralsDesc')}>
                <div className="flex gap-1">
                  {NUMERAL_STYLES.map((option) => (
                    <Button
                      key={option}
                      size="sm"
                      variant={numerals === option ? 'primary' : 'secondary'}
                      aria-pressed={numerals === option}
                      onClick={() => setNumerals(option)}
                    >
                      {t(`numeralOptions.${option}`)}
                    </Button>
                  ))}
                </div>
              </Row>

              <Row label={t('language')} description={t('languageDesc')}>
                <div className="flex flex-wrap gap-1">
                  {LANGUAGES.map((option) => (
                    <Button
                      key={option.code}
                      size="sm"
                      variant={locale === option.code ? 'primary' : 'secondary'}
                      onClick={() => setLocale(option.code)}
                    >
                      <span className="me-1">{option.flag}</span>
                      {tc(option.nameKey)}
                    </Button>
                  ))}
                </div>
              </Row>
            </section>

            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">{t('window')}</h2>

              <Row label={t('minimizeToTray')} description={t('minimizeToTrayDesc')}>
                <Button
                  size="sm"
                  variant={minimizeToTray ? 'primary' : 'secondary'}
                  aria-pressed={minimizeToTray}
                  onClick={() => setMinimizeToTray((v) => !v)}
                >
                  {minimizeToTray ? tc('generic.on') : tc('generic.off')}
                </Button>
              </Row>

              <Row label={t('closeToTray')} description={t('closeToTrayDesc')}>
                <Button
                  size="sm"
                  variant={closeToTray ? 'primary' : 'secondary'}
                  aria-pressed={closeToTray}
                  onClick={() => setCloseToTray((v) => !v)}
                >
                  {closeToTray ? tc('generic.on') : tc('generic.off')}
                </Button>
              </Row>
            </section>

            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">{t('workspace')}</h2>

              <Row label={t('workspaceFolder')} description={workspaceRoot ?? t('noWorkspace')}>
                <Button size="sm" onClick={() => void chooseWorkspace()}>
                  {tc('generic.choose')}
                </Button>
              </Row>
            </section>

            {/* S05: plan, usage, and model route */}
            <section>
              <h2 className="pb-2 text-h2 font-semibold text-fg-primary">{t('billing.title')}</h2>
              <p className="pb-2 text-caption text-fg-secondary">{t('billing.desc')}</p>
              <BillingSummary />
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
