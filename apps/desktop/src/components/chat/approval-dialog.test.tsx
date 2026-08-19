/**
 * Tests for the ApprovalDialog component (S07).
 *
 * Covers the three decisions: allow_once, allow_always_session, deny.
 * Also verifies fail-closed behaviour: without an explicit approver the
 * dialog blocks (no auto-approve).
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalDialog } from '@/components/chat/approval-dialog';
import type { PendingApproval } from '@/types';

const approval: PendingApproval = {
  approvalId: 'appr_test_01',
  toolName: 'write_file',
  argsSummary: '{"path": "/tmp/test.txt"}',
  risk: 'dangerous',
  paneId: 'pane-1',
};

describe('ApprovalDialog', () => {
  it('renders the tool name and args summary', () => {
    render(<ApprovalDialog approval={approval} onDecision={vi.fn()} />);
    expect(screen.getByText('write_file')).toBeDefined();
    expect(screen.getByText('{"path": "/tmp/test.txt"}')).toBeDefined();
  });

  it('renders locale-backed button labels (English)', () => {
    render(<ApprovalDialog approval={approval} onDecision={vi.fn()} />);
    expect(screen.getByText('Allow once')).toBeDefined();
    expect(screen.getByText('Always allow this tool this session')).toBeDefined();
    expect(screen.getByText('Deny')).toBeDefined();
  });

  it('calls onDecision("allow_once") when Allow once is clicked', () => {
    const onDecision = vi.fn();
    render(<ApprovalDialog approval={approval} onDecision={onDecision} />);
    fireEvent.click(screen.getByText('Allow once'));
    expect(onDecision).toHaveBeenCalledWith('allow_once');
  });

  it('calls onDecision("allow_always_session") when Always allow is clicked', () => {
    const onDecision = vi.fn();
    render(<ApprovalDialog approval={approval} onDecision={onDecision} />);
    fireEvent.click(screen.getByText('Always allow this tool this session'));
    expect(onDecision).toHaveBeenCalledWith('allow_always_session');
  });

  it('calls onDecision("deny") when Deny is clicked', () => {
    const onDecision = vi.fn();
    render(<ApprovalDialog approval={approval} onDecision={onDecision} />);
    fireEvent.click(screen.getByText('Deny'));
    expect(onDecision).toHaveBeenCalledWith('deny');
  });

  it('calls onDecision("deny") on Escape key', () => {
    const onDecision = vi.fn();
    render(<ApprovalDialog approval={approval} onDecision={onDecision} />);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onDecision).toHaveBeenCalledWith('deny');
  });

  it('has role="dialog" and is aria-modal', () => {
    render(<ApprovalDialog approval={approval} onDecision={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', 'Approval Required: write_file');
  });
});
