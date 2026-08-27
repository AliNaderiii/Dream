/**
 * Tests for the ApprovalDialog component (S07).
 *
 * Covers Allow once and Deny. Always Allow / YOLO are refused.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApprovalDialog } from '@/components/chat/approval-dialog';
import { i18n } from '@/lib/i18n';
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
    expect(screen.queryByText('Always allow this tool this session')).toBeNull();
    expect(screen.getByText('Deny')).toBeDefined();
  });

  it('calls onDecision("allow_once") when Allow once is clicked', () => {
    const onDecision = vi.fn();
    render(<ApprovalDialog approval={approval} onDecision={onDecision} />);
    fireEvent.click(screen.getByText('Allow once'));
    expect(onDecision).toHaveBeenCalledWith('allow_once');
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
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' });
    expect(onDecision).toHaveBeenCalledWith('deny');
  });

  it('renders the generated Persian approval choices', async () => {
    await i18n.changeLanguage('fa');
    const view = render(<ApprovalDialog approval={approval} onDecision={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'یک‌بار اجازه بده' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'همیشه اجازه بده (این نشست)' })).toBeNull();
    expect(screen.getByRole('button', { name: 'رد کردن' })).toBeInTheDocument();
    view.unmount();
    await i18n.changeLanguage('en');
  });

  it('uses modal alertdialog semantics, begins on allow once, and traps focus', async () => {
    const user = userEvent.setup();
    render(<ApprovalDialog approval={approval} onDecision={vi.fn()} />);
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', 'Approval Required: write_file');
    const allowOnce = screen.getByRole('button', { name: 'Allow once' });
    await waitFor(() => expect(allowOnce).toHaveFocus());
    await user.tab();
    expect(screen.getByRole('button', { name: 'Deny' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(allowOnce).toHaveFocus();
  });
});
