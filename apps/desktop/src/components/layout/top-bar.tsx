/**
 * Top bar: sidebar toggle, page title, model selector and quick actions.
 */

import { Bell, FolderOpen, Moon, PanelLeftOpen, Plus, Sun } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { dialogApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import { useProviderStore } from '@/stores/use-provider-store';
import { useSessionStore } from '@/stores/use-session-store';
import { formatShortcut } from '@/utils/platform';

interface TopBarProps {
  /** Title of the active screen. */
  title: string;
}

export function TopBar({ title }: TopBarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const isPaneWorkspace = location.pathname === '/chat' || location.pathname.startsWith('/chat/');
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const resolvedTheme = useAppStore((s) => s.resolvedTheme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const pendingApprovals = useAppStore((s) => s.pendingApprovals);
  const setWorkspaceRoot = useAppStore((s) => s.setWorkspaceRoot);

  const providers = useProviderStore((s) => s.providers);
  const activeProviderId = useProviderStore((s) => s.activeProviderId);
  const activeModelId = useProviderStore((s) => s.activeModelId);
  const setActiveProvider = useProviderStore((s) => s.setActiveProvider);
  const createSession = useSessionStore((s) => s.createSession);

  const activeProvider = providers.find((p) => p.id === activeProviderId);

  const chooseWorkspace = async () => {
    const folder = await dialogApi.selectFolder({ title: 'Choose workspace folder' });
    if (!folder) return;
    await dialogApi.setWorkspaceRoot(folder);
    setWorkspaceRoot(folder);
  };

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border-default bg-surface px-3">
      {collapsed && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Expand sidebar"
              onClick={toggleSidebar}
            >
              <PanelLeftOpen aria-hidden className="rtl:rotate-180" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Expand sidebar {formatShortcut(['mod', 'b'])}</TooltipContent>
        </Tooltip>
      )}

      <h1 className="flex-1 truncate text-h3 font-semibold">{title}</h1>

      {!isPaneWorkspace && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" className="gap-1.5">
              <span className="truncate">{activeProvider?.name ?? 'Select model'}</span>
              {activeModelId && <span className="ltr-island text-fg-muted">{activeModelId}</span>}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-56">
            <DropdownMenuLabel>Providers</DropdownMenuLabel>
            {providers.map((provider) => (
              <DropdownMenuCheckboxItem
                key={provider.id}
                checked={provider.id === activeProviderId}
                onCheckedChange={() => setActiveProvider(provider.id)}
              >
                <span className="flex-1">{provider.name}</span>
                <Badge variant={provider.local ? 'success' : 'neutral'}>
                  {provider.local ? 'Local' : 'Cloud'}
                </Badge>
              </DropdownMenuCheckboxItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem
              checked={false}
              onCheckedChange={() => void navigate('/providers')}
            >
              Configure providers…
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="New session"
            onClick={() => {
              const session = createSession();
              void navigate(`/chat/${session.id}`);
            }}
          >
            <Plus aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>New session {formatShortcut(['mod', 'n'])}</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Choose workspace"
            onClick={() => void chooseWorkspace()}
          >
            <FolderOpen aria-hidden />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Choose workspace folder</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Pending approvals: ${pendingApprovals}`}
            className="relative"
          >
            <Bell aria-hidden />
            {pendingApprovals > 0 && (
              <span className="absolute end-0.5 top-0.5 size-2 rounded-full bg-danger-fg" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {pendingApprovals === 0
            ? 'No pending approvals'
            : `${pendingApprovals} pending approvals`}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={resolvedTheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            onClick={toggleTheme}
          >
            {resolvedTheme === 'dark' ? <Sun aria-hidden /> : <Moon aria-hidden />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>Toggle theme {formatShortcut(['mod', 'shift', 'l'])}</TooltipContent>
      </Tooltip>
    </div>
  );
}
