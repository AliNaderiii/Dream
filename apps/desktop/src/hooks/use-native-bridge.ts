/**
 * Wires Rust-side events and one-time native setup into the React tree.
 *
 * Handles: initial state hydration, agent status / approval-count events, tray
 * menu actions, and the first-launch notification permission request.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useTranslation } from '@/lib/i18n';
import { appApi, events, listen, notificationApi } from '@/lib/tauri';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { AgentStatus } from '@/types';
import { isTauri } from '@/utils/platform';

/** Marks that permission has been requested, so it happens only once per install. */
const PERMISSION_KEY = 'dream.notifications.requested';

/**
 * Subscribes to native events. Mount once, at the app root.
 */
export function useNativeBridge(): void {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const setAgentStatus = useAppStore((s) => s.setAgentStatus);
  const setPendingApprovals = useAppStore((s) => s.setPendingApprovals);
  const setWorkspaceRoot = useAppStore((s) => s.setWorkspaceRoot);
  const toggleCommandPalette = useAppStore((s) => s.toggleCommandPalette);
  const createSession = useSessionStore((s) => s.createSession);

  // Hydrate from Rust state on mount.
  useEffect(() => {
    if (!isTauri()) return;
    let cancelled = false;

    void appApi.getState().then((state) => {
      if (cancelled || !state) return;
      setAgentStatus(state.agentStatus);
      setPendingApprovals(state.pendingApprovals);
      setWorkspaceRoot(state.workspaceRoot);
    });

    return () => {
      cancelled = true;
    };
  }, [setAgentStatus, setPendingApprovals, setWorkspaceRoot]);

  // Request notification permission once, on first launch.
  useEffect(() => {
    if (!isTauri()) return;
    if (localStorage.getItem(PERMISSION_KEY)) return;
    localStorage.setItem(PERMISSION_KEY, '1');
    void notificationApi.requestPermission();
  }, []);

  // Agent status and approval count pushed from Rust.
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    void listen<AgentStatus>(events.agentStatus, setAgentStatus).then((un) => unlisteners.push(un));
    void listen<number>(events.approvals, setPendingApprovals).then((un) => unlisteners.push(un));

    return () => unlisteners.forEach((un) => un());
  }, [setAgentStatus, setPendingApprovals]);

  // Tray menu actions that need the router or React state.
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    void listen(events.trayNewSession, () => {
      const session = createSession(t('sessions.untitled'));
      void navigate(`/chat/${session.id}`);
    }).then((un) => unlisteners.push(un));

    void listen(events.trayQuickAsk, () => {
      toggleCommandPalette();
    }).then((un) => unlisteners.push(un));

    return () => unlisteners.forEach((un) => un());
  }, [navigate, createSession, t, toggleCommandPalette]);
}
