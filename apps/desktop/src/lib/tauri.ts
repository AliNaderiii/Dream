/**
 * Typed wrapper around the Rust command surface.
 *
 * Every function degrades gracefully outside Tauri (browser dev server, unit
 * tests) by returning a sensible default instead of throwing, so the UI can be
 * developed and tested without the native shell.
 */

import { invoke as tauriInvoke } from '@tauri-apps/api/core';
import { listen as tauriListen, type UnlistenFn } from '@tauri-apps/api/event';

import type {
  AgentStatus,
  AppStateSnapshot,
  FileEntry,
  NotificationPermission,
  NotificationRequest,
  SendOutcome,
} from '@/types';
import { isTauri } from '@/utils/platform';

/** Invokes a Rust command, returning `fallback` when not running under Tauri. */
async function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T | undefined>;
async function invoke<T>(
  cmd: string,
  args: Record<string, unknown> | undefined,
  fallback: T,
): Promise<T>;
async function invoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
  fallback?: T,
): Promise<T | undefined> {
  if (!isTauri()) return fallback;
  try {
    return await tauriInvoke<T>(cmd, args);
  } catch (error) {
    console.error(`[dream] command \`${cmd}\` failed:`, error);
    throw error;
  }
}

/** Subscribes to a Tauri event; a no-op unsubscribe is returned in the browser. */
export async function listen<T>(event: string, handler: (payload: T) => void): Promise<UnlistenFn> {
  if (!isTauri()) return () => {};
  return tauriListen<T>(event, (e) => handler(e.payload));
}

/* ------------------------------------------------------------------ window */

export const windowApi = {
  /** Minimises the current window (or hides it when minimise-to-tray is on). */
  minimize: (label?: string) => invoke<void>('minimize_window', { label }),
  /** Toggles maximise; resolves to the new maximised state. */
  toggleMaximize: (label?: string) => invoke<boolean>('toggle_maximize', { label }, false),
  /** Toggles fullscreen; resolves to the new fullscreen state. */
  toggleFullscreen: (label?: string) => invoke<boolean>('toggle_fullscreen', { label }, false),
  /** Closes a window (the main window hides to tray when configured). */
  close: (label?: string) => invoke<void>('close_window', { label }),
  /** Shows, unminimises and focuses a window. */
  focus: (label?: string) => invoke<void>('focus_window', { label }),
  /** Opens an additional window at `route`; resolves to its label. */
  open: (options: { label?: string; route?: string; title?: string } = {}) =>
    invoke<string>('open_window', options, ''),
  /** Lists the labels of all open windows. */
  list: () => invoke<string[]>('list_windows', undefined, []),
  /** Enables or disables hiding to tray on minimise. */
  setMinimizeToTray: (enabled: boolean) => invoke<void>('set_minimize_to_tray', { enabled }),
  /** Enables or disables hiding to tray on close. */
  setCloseToTray: (enabled: boolean) => invoke<void>('set_close_to_tray', { enabled }),
};

/* ------------------------------------------------------------- app / tray */

export const appApi = {
  /** Reads the Rust-side state snapshot. */
  getState: () =>
    invoke<AppStateSnapshot>('get_app_state', undefined, {
      agentStatus: 'idle',
      pendingApprovals: 0,
      workspaceRoot: null,
      minimizeToTray: false,
      closeToTray: true,
    }),
  /** Updates agent status; refreshes the tray tooltip and Pause/Resume items. */
  setAgentStatus: (status: AgentStatus) => invoke<void>('set_agent_status', { status }),
  /** Updates the pending-approval count; refreshes the tray badge. */
  setPendingApprovals: (count: number) => invoke<void>('set_pending_approvals', { count }),
};

/* ----------------------------------------------------------- notifications */

export const notificationApi = {
  /** Reads the current permission without prompting. */
  permission: () => invoke<NotificationPermission>('notification_permission', undefined, 'prompt'),
  /** Requests permission, prompting when undecided. */
  requestPermission: () =>
    invoke<NotificationPermission>('request_notification_permission', undefined, 'denied'),
  /** Sends a native notification; duplicates within 5s of the same id are skipped. */
  send: (request: NotificationRequest) =>
    invoke<SendOutcome>('send_notification', { request }, 'denied'),
};

/* ----------------------------------------------------------------- dialogs */

export const dialogApi = {
  /** Native "Open file" dialog. Empty array means cancelled. */
  openFile: (options: { multiple?: boolean; title?: string } = {}) =>
    invoke<FileEntry[]>('open_file_dialog', options, []),
  /** Native "Save file" dialog. `null` means cancelled. */
  saveFile: (options: { defaultName?: string; title?: string } = {}) =>
    invoke<string | null>('save_file_dialog', options, null),
  /** Native folder picker, used for workspace selection. `null` means cancelled. */
  selectFolder: (options: { title?: string } = {}) =>
    invoke<string | null>('select_folder_dialog', options, null),
  /** Sets the workspace root that scopes path validation. */
  setWorkspaceRoot: (path: string | null) => invoke<void>('set_workspace_root', { path }),
  /** Validates dropped paths, dropping any that fail the scope check. */
  validatePaths: (paths: string[]) => invoke<FileEntry[]>('validate_paths', { paths }, []),
};

/** Event names emitted by the Rust side. */
export const events = {
  agentStatus: 'agent://status',
  approvals: 'agent://approvals',
  trayNewSession: 'tray://new-session',
  trayQuickAsk: 'tray://quick-ask',
  trayQuit: 'tray://quit',
} as const;
