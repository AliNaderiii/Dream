/**
 * The Dream bridge — the ONLY link between the UI and the Python core.
 *
 * Protocol (unchanged from the Rust shell): `bridge_send(id, method, params)`
 * over Tauri IPC, JSON results with snake_case fields.
 *
 * The honesty rule of v5: there is NO echo layer, NO simulated fallback,
 * NO demo data. If the core is unreachable the caller gets
 * `BridgeUnavailableError` and the UI says so. Every result the UI shows
 * came from the real Python core — or it is labelled as unavailable.
 */

import { invoke } from '@tauri-apps/api/core';

export class BridgeUnavailableError extends Error {
  constructor(message = 'هسته پایتون در دسترس نیست') {
    super(message);
    this.name = 'BridgeUnavailableError';
  }
}

/** True only inside the Tauri WebView (installer / `tauri dev`). */
export const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

let nextId = 1;

/**
 * Call a bridge method. Bounded by a timeout so the UI never hangs silently.
 * @returns {Promise<any>} the JSON result from the Python core
 */
export async function call(method, params = {}, { timeoutMs = 60_000 } = {}) {
  if (!isTauri) {
    throw new BridgeUnavailableError(
      'هسته فقط داخل اپلیکیشن دسکتاپ در دسترس است — این پیش‌نمایش مرورگر است',
    );
  }
  const id = nextId++;
  let timer;
  try {
    return await Promise.race([
      invoke('bridge_send', { id, method, params }),
      new Promise((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new BridgeUnavailableError(
                `پاسخی از هسته نیامد (${method} — ${timeoutMs / 1000}s)`,
              ),
            ),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/** Connection state of the sidecar: 'ready' | 'down' | 'browser'. */
export async function status() {
  if (!isTauri) return 'browser';
  try {
    const s = await invoke('bridge_status');
    // ConnectionState fields vary by shell version; any truthy answer means
    // the supervisor and the sidecar are alive.
    return s && (s.state === undefined || s.state !== 'error') ? 'ready' : 'down';
  } catch {
    return 'down';
  }
}

/** Namespace the typed helpers the views actually use (wired in phase 2). */
export const api = {
  /** stt.transcribe — real faster-whisper in the core, or an honest error. */
  sttTranscribe: (filePath, language = 'fa') =>
    call('stt.transcribe', { file_path: filePath, language }),

  /** ocr.extract — Persian OCR over an image/PDF path. */
  ocrExtract: (filePath) => call('ocr.extract', { file_path: filePath }),

  /** pdf.export_report — shaped Persian PDF from content blocks. */
  pdfExport: (payload) => call('pdf.export_report', payload),

  /** dataqa.ask — grounded Q&A over a loaded dataset. */
  dataAsk: (question, dataset) =>
    call('dataqa.ask', { question, dataset: dataset || null }),

  /** data.load_data — list what the core can see. */
  dataLoad: (path) => call('data.load_data', { path }),
};
