/**
 * Tests for the pane chat store's S07 additions: tool cards, approval
 * state, and the "always allow" session-scoped set.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { usePaneChatStore } from '@/stores/use-pane-chat-store';
import type { ToolCardEntry } from '@/types';

const PANE = 'pane-test-1';

beforeEach(() => {
  usePaneChatStore.setState({ transcripts: {} });
});

describe('usePaneChatStore — S07 approval & tool cards', () => {
  it('starts with no pending approval', () => {
    usePaneChatStore.getState().ensure(PANE);
    const t = usePaneChatStore.getState().transcripts[PANE];
    expect(t?.pendingApproval).toBeNull();
  });

  it('setPendingApproval stores and clears', () => {
    usePaneChatStore.getState().ensure(PANE);
    const { setPendingApproval } = usePaneChatStore.getState();

    setPendingApproval(PANE, {
      approvalId: 'appr-1',
      toolName: 'write_file',
      argsSummary: '{}',
      risk: 'dangerous',
      paneId: PANE,
    });
    expect(usePaneChatStore.getState().transcripts[PANE]?.pendingApproval?.toolName).toBe(
      'write_file',
    );

    setPendingApproval(PANE, null);
    expect(usePaneChatStore.getState().transcripts[PANE]?.pendingApproval).toBeNull();
  });

  it('alwaysAllowTool adds to the set and isAlwaysAllowed checks it', () => {
    usePaneChatStore.getState().ensure(PANE);
    const { alwaysAllowTool, isAlwaysAllowed } = usePaneChatStore.getState();

    expect(isAlwaysAllowed(PANE, 'write_file')).toBe(false);

    alwaysAllowTool(PANE, 'write_file');
    expect(usePaneChatStore.getState().isAlwaysAllowed(PANE, 'write_file')).toBe(true);
    expect(usePaneChatStore.getState().isAlwaysAllowed(PANE, 'read_file')).toBe(false);
  });

  it('addMessage attaches tool cards to a message', () => {
    usePaneChatStore.getState().ensure(PANE);
    const { addMessage } = usePaneChatStore.getState();

    const card: ToolCardEntry = {
      id: 'tc-1',
      name: 'calculate',
      argsSummary: '{"expression":"1+1"}',
      status: 'ok',
      resultExcerpt: '2',
    };

    addMessage(PANE, {
      id: 'msg-1',
      role: 'assistant',
      content: '',
      createdAt: Date.now(),
      toolCards: [card],
    });

    const messages = usePaneChatStore.getState().transcripts[PANE]?.messages;
    expect(messages).toHaveLength(1);
    expect(messages?.[0].toolCards).toHaveLength(1);
    expect(messages?.[0].toolCards?.[0].name).toBe('calculate');
    expect(messages?.[0].toolCards?.[0].status).toBe('ok');
  });

  it('blocked tool card has status "blocked"', () => {
    usePaneChatStore.getState().ensure(PANE);
    const { addMessage } = usePaneChatStore.getState();

    const card: ToolCardEntry = {
      id: 'tc-blocked-1',
      name: 'run_shell',
      argsSummary: 'rm -rf /',
      status: 'blocked',
      resultExcerpt: 'Denied by user',
    };

    addMessage(PANE, {
      id: 'msg-blocked',
      role: 'assistant',
      content: '',
      createdAt: Date.now(),
      toolCards: [card],
    });

    const stored = usePaneChatStore.getState().transcripts[PANE]?.messages?.[0]?.toolCards?.[0];
    expect(stored?.status).toBe('blocked');
    expect(stored?.resultExcerpt).toBe('Denied by user');
  });

  it('fail-closed: without approver, no approval is auto-resolved', () => {
    // This test verifies the store holds no pre-set approval.
    // The actual fail-closed guarantee is in the Python ApprovalPolicy,
    // but the frontend must not auto-approve either.
    usePaneChatStore.getState().ensure(PANE);
    const t = usePaneChatStore.getState().transcripts[PANE];
    expect(t?.pendingApproval).toBeNull();
    expect(t?.alwaysAllowTools.size).toBe(0);
  });
});
