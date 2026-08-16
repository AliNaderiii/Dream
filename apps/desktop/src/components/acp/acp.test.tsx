import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ACPConfigSection } from './acp-config-section';
import type { ACPAgentDto } from '@/lib/bridge/types';

describe('ACP UI Components', () => {
  const mockAgents: ACPAgentDto[] = [
    {
      id: 'claude_code',
      name: 'Claude Code (ACP)',
      endpoint: 'http://localhost:8001',
      label: 'Claude Code',
      description: 'Anthropic Claude Code agent via local ACP bridge',
      enabled: true,
      status: 'ready',
    },
  ];

  it('renders inbound ACP server info and external agents', async () => {
    const onTest = vi.fn().mockResolvedValue(undefined);
    const onRemove = vi.fn();
    const onAdd = vi.fn();

    render(
      <ACPConfigSection
        agents={mockAgents}
        onAddAgent={onAdd}
        onRemoveAgent={onRemove}
        onTestAgent={onTest}
      />,
    );

    expect(screen.getByText(/Inbound ACP Server/i)).toBeInTheDocument();
    expect(screen.getByText('Agent Client Protocol v1.0')).toBeInTheDocument();
    expect(screen.getByText('Claude Code (ACP)')).toBeInTheDocument();
    expect(screen.getByText('Endpoint: http://localhost:8001')).toBeInTheDocument();

    const testBtn = screen.getByRole('button', { name: /Test Connection/i });
    await userEvent.click(testBtn);
    expect(onTest).toHaveBeenCalledWith('claude_code');
  });
});
