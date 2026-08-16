import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MCPServersList } from './mcp-servers-list';
import { MCPToolsList } from './mcp-tools-list';
import type { MCPServerDto, MCPToolDto } from '@/lib/bridge/types';

describe('MCP UI Components', () => {
  const mockServers: MCPServerDto[] = [
    {
      id: 'mcp_sqlite',
      name: 'SQLite Server',
      type: 'stdio',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-sqlite'],
      enabled: true,
      disabled_tools: [],
      status: 'connected',
      is_connected: true,
    },
  ];

  const mockTools: MCPToolDto[] = [
    {
      name: 'query_db',
      description: 'Execute SQL select query',
      input_schema: { type: 'object', properties: { sql: { type: 'string' } } },
      server_id: 'mcp_sqlite',
      server_name: 'SQLite Server',
      enabled: true,
      risk: 'guarded',
    },
  ];

  it('renders MCP server list and test connection button', async () => {
    const onTest = vi.fn().mockResolvedValue(undefined);
    const onToggle = vi.fn();
    const onRemove = vi.fn();
    const onAdd = vi.fn();

    render(
      <MCPServersList
        servers={mockServers}
        tools={mockTools}
        onAddServer={onAdd}
        onRemoveServer={onRemove}
        onToggleServer={onToggle}
        onTestConnection={onTest}
      />,
    );

    expect(screen.getByText('SQLite Server')).toBeInTheDocument();
    expect(screen.getByText('STDIO')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();

    const testBtn = screen.getByRole('button', { name: /Test/i });
    await userEvent.click(testBtn);
    expect(onTest).toHaveBeenCalledWith('mcp_sqlite');
  });

  it('renders MCP tools list and handles tool toggle', async () => {
    const onToggle = vi.fn();
    render(<MCPToolsList tools={mockTools} onToggleTool={onToggle} />);

    expect(screen.getByText('query_db')).toBeInTheDocument();
    expect(screen.getByText('Execute SQL select query')).toBeInTheDocument();

    const switchBtn = screen.getByRole('switch');
    await userEvent.click(switchBtn);
    expect(onToggle).toHaveBeenCalledWith('mcp_sqlite', 'query_db', false);
  });
});
