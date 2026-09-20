/**
 * Echo runtime for the Telegram report bot bridge (`reportbot.*`) — honest
 * deterministic demo state for the browser preview, where no Python sidecar
 * (and therefore no real Telegram poller) runs.
 */

import type { ReportBotEvent, ReportBotStatus } from './reportbot';

const now = () => Math.round(Date.now() / 1000);

const DEMO_EVENTS: ReportBotEvent[] = [
  {
    ts: now() - 240,
    kind: 'started',
    chat_id: null,
    detail: {},
  },
  {
    ts: now() - 200,
    kind: 'photo_report',
    chat_id: 42,
    detail: { ocr_chars: 214, fields: 5, pdf_pages: 1, pdf_bytes: 18_402 },
  },
  {
    ts: now() - 90,
    kind: 'voice_report',
    chat_id: 42,
    detail: { transcript_chars: 96, duration_s: 11, pdf_pages: 1 },
  },
  {
    ts: now() - 12,
    kind: 'text_report',
    chat_id: 42,
    detail: { text_chars: 74, pdf_pages: 1 },
  },
];

/** Deterministic demo of `reportbot.start` for the echo transport. */
export function echoReportBotStart(token: string): ReportBotStatus {
  const fingerprint = token.length > 4 ? `…${token.slice(-4)}` : '…';
  return {
    running: true,
    connected: true,
    started_at: now() - 240,
    updates_processed: 3,
    last_error: null,
    token_fingerprint: fingerprint,
    stt_engine: 'simulated (demo)',
    events: DEMO_EVENTS,
    demo: true,
  };
}

/** Deterministic demo of `reportbot.stop` for the echo transport. */
export function echoReportBotStop(): ReportBotStatus {
  return {
    running: false,
    connected: false,
    started_at: null,
    updates_processed: 3,
    last_error: null,
    token_fingerprint: null,
    stt_engine: 'simulated (demo)',
    events: [...DEMO_EVENTS, { ts: now(), kind: 'stopped', chat_id: null, detail: {} }],
    demo: true,
  };
}

/** Deterministic demo of `reportbot.status` for the echo transport. */
export function echoReportBotStatus(): ReportBotStatus {
  return {
    running: false,
    connected: false,
    started_at: null,
    updates_processed: 0,
    last_error: null,
    token_fingerprint: null,
    stt_engine: 'simulated (demo)',
    events: [],
    demo: true,
  };
}
