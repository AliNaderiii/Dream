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
              new BridgeUnavailableError(`پاسخی از هسته نیامد (${method} — ${timeoutMs / 1000}s)`),
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
    return s && (s.state === undefined || s.state !== 'error') ? 'ready' : 'down';
  } catch {
    return 'down';
  }
}

/**
 * Pick a file with the native dialog. Returns a FileEntry
 * ({path, name, extension, size, is_dir}) or null when cancelled.
 * Browser preview: honest error — no fake paths.
 */
export async function pickFile(title = 'انتخاب فایل') {
  if (!isTauri) {
    throw new BridgeUnavailableError(
      'انتخاب فایل فقط داخل اپلیکیشن دسکتاپ ممکن است — در پیش‌نمایش مرورگر مسیر واقعی وجود ندارد',
    );
  }
  const entries = await invoke('open_file_dialog', { multiple: false, title });
  return entries?.[0] ?? null;
}

/** Default sibling output path for a generated PDF: <source>.report.pdf */
export function pdfSiblingPath(sourcePath, suffix = 'report') {
  const base = String(sourcePath).replace(/\.[^.\\/]*$/, '');
  return `${base}.${suffix}.pdf`;
}

/** Pick a folder with the native dialog. Returns an absolute path or null. */
export async function pickFolder(title = 'انتخاب پوشه') {
  if (!isTauri) {
    throw new BridgeUnavailableError('انتخاب پوشه فقط داخل اپلیکیشن دسکتاپ ممکن است');
  }
  return invoke('select_folder_dialog', { title });
}

/** Namespace of the typed helpers the views use — all REAL core methods. */
export const api = {
  // ---- speech-to-text ----------------------------------------------------
  /** stt.transcribe — real faster-whisper in the core, or an honest error. */
  sttTranscribe: (filePath, language = 'fa') =>
    call('stt.transcribe', { file_path: filePath, language }, { timeoutMs: 300_000 }),

  // ---- text-to-speech ----------------------------------------------------
  /** tts.engines — honest engine listing (edge online / piper offline). */
  ttsEngines: () => call('tts.engines', {}, { timeoutMs: 30_000 }),

  /** tts.voices — voice catalogue per engine (with on-disk flags). */
  ttsVoices: (engine = '') => call('tts.voices', { engine }, { timeoutMs: 30_000 }),

  /** tts.synthesize — text → real speech; result carries inline audio. */
  ttsSynthesize: (
    text,
    { engine = 'auto', voice = '', speed = 1, outputPath = '', withAudio = true } = {},
  ) =>
    call(
      'tts.synthesize',
      { text, engine, voice, speed, output_path: outputPath, with_audio: withAudio },
      { timeoutMs: 120_000 },
    ),

  // ---- web reading (human-in-the-loop) ------------------------------------
  /** browse.propose — queue a URL; nothing is fetched until you approve. */
  browsePropose: (url) => call('browse.propose', { url }, { timeoutMs: 30_000 }),

  /** browse.list — proposed/fetched/denied drafts. */
  browseList: () => call('browse.list', {}, { timeoutMs: 30_000 }),

  /** browse.approve — your explicit approval; the core then fetches. */
  browseApprove: (draftId) =>
    call('browse.approve', { draft_id: draftId, approved: true }, { timeoutMs: 120_000 }),

  /** browse.deny — refuse a pending URL. */
  browseDeny: (draftId) => call('browse.deny', { draft_id: draftId }, { timeoutMs: 30_000 }),

  /** browse.follow — propose a link extracted from a fetched page. */
  browseFollow: (draftId, url) =>
    call('browse.follow', { draft_id: draftId, url }, { timeoutMs: 30_000 }),

  // ---- code sandbox -------------------------------------------------------
  /** sandbox.run_code — real Python in the stateful core sandbox. */
  sandboxRun: (code, timeoutSeconds = 15) =>
    call('sandbox.run_code', { code, timeout_seconds: timeoutSeconds }, { timeoutMs: 180_000 }),

  /** sandbox.get_status — executions, variables, artifacts. */
  sandboxStatus: () => call('sandbox.get_status', {}, { timeoutMs: 30_000 }),

  /** sandbox.reset — clear the stateful namespace. */
  sandboxReset: () => call('sandbox.reset', {}, { timeoutMs: 30_000 }),

  // ---- workspace files ---------------------------------------------------
  /** workspace.roots_list — registered workspace roots. */
  wsRootsList: () => call('workspace.roots_list', {}, { timeoutMs: 30_000 }),

  /** workspace.roots_register — explicit user action via the native dialog. */
  wsRootsRegister: (folder, name = '') =>
    call('workspace.roots_register', { folder, name }, { timeoutMs: 60_000 }),

  /** workspace.files_list — bounded, symlink-safe listing inside one root. */
  wsFilesList: (rootId, path = '', cursor = 0) =>
    call(
      'workspace.files_list',
      { root_id: rootId, path, cursor, limit: 200 },
      { timeoutMs: 60_000 },
    ),

  /** workspace.files_preview — bounded text preview (truncated flag). */
  wsFilesPreview: (rootId, path) =>
    call('workspace.files_preview', { root_id: rootId, path }, { timeoutMs: 30_000 }),

  // ---- screen vision ------------------------------------------------------
  /** vision.capture_screen — real GDI capture + core OCR; temp file deleted. */
  visionCaptureScreen: (documentType = 'general') =>
    call('vision.capture_screen', { document_type: documentType }, { timeoutMs: 120_000 }),

  // ---- OCR ---------------------------------------------------------------
  /** ocr.extract — document_type: general | invoice | receipt | id_card. */
  ocrExtract: (filePath, documentType = 'general') =>
    call(
      'ocr.extract',
      { file_path: filePath, document_type: documentType },
      { timeoutMs: 180_000 },
    ),

  /** ocr.extract_invoice — invoice key-value fields. */
  ocrInvoice: (filePath) =>
    call('ocr.extract_invoice', { file_path: filePath }, { timeoutMs: 180_000 }),

  // ---- Persian PDF -------------------------------------------------------
  /** pdf.export_report — report {title, subtitle?, sections[]}, output_path. */
  pdfExport: (report, outputPath) =>
    call('pdf.export_report', { report, output_path: outputPath }, { timeoutMs: 120_000 }),

  // ---- data Q&A ----------------------------------------------------------
  /** dataqa.sessions.create — {source} path to CSV/JSON/SQLite. */
  dataSessionCreate: (source) => call('dataqa.sessions.create', { source }, { timeoutMs: 120_000 }),

  /** dataqa.sessions.list — loaded sessions. */
  dataSessionsList: () => call('dataqa.sessions.list', {}, { timeoutMs: 30_000 }),

  /** dataqa.ask — {session_id, question}; final result carries evidence. */
  dataAsk: (sessionId, question) =>
    call('dataqa.ask', { session_id: sessionId, question, timeout: 20 }, { timeoutMs: 90_000 }),

  // ---- Telegram report bot ----------------------------------------------
  reportbotStart: (token) => call('reportbot.start', { token }, { timeoutMs: 30_000 }),

  reportbotStop: () => call('reportbot.stop', {}, { timeoutMs: 30_000 }),

  reportbotStatus: () => call('reportbot.status', {}, { timeoutMs: 15_000 }),

  // ---- episodic memory ---------------------------------------------------
  /** episodic.query_timeline — {query, limit}. */
  episodicQuery: (query, limit = 50) =>
    call('episodic.query_timeline', { query, limit }, { timeoutMs: 60_000 }),

  /** episodic.get_hierarchy_stats — tier metrics. */
  episodicStats: () => call('episodic.get_hierarchy_stats', {}, { timeoutMs: 30_000 }),

  /** episodic.record_event — {session_id, speaker, text}. */
  episodicRecord: (sessionId, speaker, text) =>
    call('episodic.record_event', { session_id: sessionId, speaker, text }, { timeoutMs: 30_000 }),

  // ---- research ----------------------------------------------------------
  /** research.create — {topic, workspace} → session summary. */
  researchCreate: (topic, workspace) =>
    call('research.create', { topic, workspace }, { timeoutMs: 60_000 }),

  /** research.plan — runs the planner; leaves the session APPROVAL_PENDING. */
  researchPlan: (sessionId, force = false) =>
    call('research.plan', { session_id: sessionId, force }, { timeoutMs: 120_000 }),

  /** research.approve — the human-in-the-loop checkpoint. */
  researchApprove: (sessionId) =>
    call('research.approve', { session_id: sessionId }, { timeoutMs: 300_000 }),

  /** research.get — full record: plan, sections, findings, report, events. */
  researchGet: (sessionId) =>
    call('research.get', { session_id: sessionId }, { timeoutMs: 60_000 }),

  /** research.list — persisted session summaries, newest first. */
  researchList: () => call('research.list', {}, { timeoutMs: 30_000 }),
};
