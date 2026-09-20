/**
 * Telegram report bot bridge — `reportbot.*`.
 *
 * In Tauri this controls the real long-polling bot inside the Python core
 * (photo → OCR, voice → transcription, text → structured report; every path
 * ends in a Persian PDF sent back to the chat). Under the echo transport
 * (browser preview / tests) it returns clearly-flagged demo state.
 */

import type { BridgeClient } from './client';
import { echoReportBotStart, echoReportBotStatus, echoReportBotStop } from './echo-reportbot';

/** One entry of the bounded server-side event log. */
export interface ReportBotEvent {
  ts: number;
  kind: string;
  chat_id: number | null;
  detail: Record<string, unknown>;
}

/** Shape of `reportbot.status` (snake_case fields from the Python core). */
export interface ReportBotStatus {
  running: boolean;
  connected: boolean;
  started_at: number | null;
  updates_processed: number;
  last_error: string | null;
  token_fingerprint: string | null;
  /** Voice-path engine: "faster-whisper" or an honest simulated label. */
  stt_engine?: string;
  events: ReportBotEvent[];
  /** Present only on echo-transport demo results. */
  demo?: boolean;
}

/** Start the report bot with a BotFather token (and optional relay base URL). */
export async function reportbotStart(
  client: BridgeClient,
  token: string,
  apiBaseUrl?: string,
): Promise<ReportBotStatus> {
  if (client.transportKind === 'echo') {
    return echoReportBotStart(token);
  }
  const payload: Record<string, unknown> = { token };
  if (apiBaseUrl && apiBaseUrl.trim()) {
    payload.api_base_url = apiBaseUrl.trim();
  }
  const result = await client.call<ReportBotStatus>('reportbot.start', payload);
  return { ...result, demo: undefined };
}

/** Stop the running report bot (idempotent). */
export async function reportbotStop(client: BridgeClient): Promise<ReportBotStatus> {
  if (client.transportKind === 'echo') {
    return echoReportBotStop();
  }
  const result = await client.call<ReportBotStatus>('reportbot.stop', {});
  return { ...result, demo: undefined };
}

/** Read running state, counters, and the bounded event log. */
export async function reportbotStatus(client: BridgeClient): Promise<ReportBotStatus> {
  if (client.transportKind === 'echo') {
    return echoReportBotStatus();
  }
  return client.call<ReportBotStatus>('reportbot.status', {});
}
