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

  // ---- reasoning tree (user-driven Tree-of-Thoughts) ----------------------
  /** reasoning.plan_tree — create a ToT trajectory for a goal. */
  reasoningPlanTree: (goal) => call('reasoning.plan_tree', { goal }, { timeoutMs: 60_000 }),

  /** reasoning.expand_branch — add YOUR candidate thoughts under a node. */
  reasoningExpand: (trajectoryId, parentNodeId, thoughts) =>
    call(
      'reasoning.expand_branch',
      { trajectory_id: trajectoryId, parent_node_id: parentNodeId, thoughts },
      { timeoutMs: 60_000 },
    ),

  /** reasoning.step_critique — rule-based critique (length/coherence/depth). */
  reasoningCritique: (trajectoryId, nodeId) =>
    call(
      'reasoning.step_critique',
      { trajectory_id: trajectoryId, node_id: nodeId },
      { timeoutMs: 60_000 },
    ),

  /** reasoning.mcts_search — one MCTS iteration over YOUR candidate thoughts. */
  reasoningMcts: (trajectoryId, candidateThoughts) =>
    call(
      'reasoning.mcts_search',
      { trajectory_id: trajectoryId, candidate_thoughts: candidateThoughts },
      { timeoutMs: 120_000 },
    ),

  /** reasoning.backtrack — prune weak branches, recompute the frontier. */
  reasoningBacktrack: (trajectoryId) =>
    call('reasoning.backtrack', { trajectory_id: trajectoryId }, { timeoutMs: 60_000 }),

  /** reasoning.synthesize_solution — assemble the winning path. */
  reasoningSynthesize: (trajectoryId) =>
    call('reasoning.synthesize_solution', { trajectory_id: trajectoryId }, { timeoutMs: 60_000 }),

  /** reasoning.get_tree_stats — live tree metrics + full node list. */
  reasoningStats: (trajectoryId) =>
    call('reasoning.get_tree_stats', { trajectory_id: trajectoryId }, { timeoutMs: 30_000 }),

  // ---- mental model (dialectic belief graph) -------------------------------
  /** dialectic.add_belief — register a belief with confidence. */
  dialecticAdd: (domain, statement) =>
    call('dialectic.add_belief', { domain, statement }, { timeoutMs: 30_000 }),

  /** dialectic.detect_tensions — rule-based contradiction pairs. */
  dialecticTensions: () => call('dialectic.detect_tensions', {}, { timeoutMs: 60_000 }),

  /** dialectic.reconcile_tension — merge with YOUR nuanced statement. */
  dialecticReconcile: (tensionId, nuancedStatement) =>
    call(
      'dialectic.reconcile_tension',
      { tension_id: tensionId, nuanced_statement: nuancedStatement },
      { timeoutMs: 30_000 },
    ),

  /** dialectic.query — keyword search over the belief graph. */
  dialecticQuery: (query, limit = 8) =>
    call('dialectic.query', { query, limit }, { timeoutMs: 30_000 }),

  /** dialectic.snapshot — counts, top beliefs, synthesized summary. */
  dialecticSnapshot: () => call('dialectic.snapshot', {}, { timeoutMs: 30_000 }),

  // ---- runtimes (provider hubs) -------------------------------------------
  /** providerhubs.runtimes — the local runtime matrix (detection/health). */
  phRuntimes: () => call('providerhubs.runtimes', {}, { timeoutMs: 30_000 }),

  /** providerhubs.catalog — local + cloud providers, filtered by query. */
  phCatalog: (query = '') => call('providerhubs.catalog', { query }, { timeoutMs: 30_000 }),

  /** providerhubs.test — bounded probe; latency back, secrets never sent. */
  phTest: (runtimeId) =>
    call('providerhubs.test', { runtime_id: runtimeId }, { timeoutMs: 30_000 }),

  /** providerhubs.models — real model listing from the runtime endpoint. */
  phModels: (runtimeId) =>
    call('providerhubs.models', { runtime_id: runtimeId }, { timeoutMs: 60_000 }),

  /** providerhubs.select_model — persisted per-runtime model choice. */
  phSelectModel: (runtimeId, model) =>
    call('providerhubs.select_model', { runtime_id: runtimeId, model }, { timeoutMs: 30_000 }),

  /** providerhubs.diagnose — bilingual firing verdict + fix hints. */
  phDiagnose: (runtimeId) =>
    call('providerhubs.diagnose', { runtime_id: runtimeId }, { timeoutMs: 30_000 }),

  /** providerhubs.route — deterministic active route, resolved offline. */
  phRoute: () => call('providerhubs.route', {}, { timeoutMs: 30_000 }),

  /** providerhubs.gateway — optional tool-gateway snapshot (keychain). */
  phGateway: () => call('providerhubs.gateway', {}, { timeoutMs: 30_000 }),

  /** providerhubs.gateway_update — toggles only; credentials are refused. */
  phGatewayUpdate: (params) => call('providerhubs.gateway_update', params, { timeoutMs: 30_000 }),

  // ---- spaces (durable project work surfaces) ------------------------------
  /** space.list — persisted space records, newest first. */
  spaceList: () => call('space.list', {}, { timeoutMs: 30_000 }),

  /** space.create — {name, language fa|en, ceiling safe|guarded}. */
  spaceCreate: (name, language = 'fa', ceiling = 'guarded') =>
    call('space.create', { name, language, ceiling }, { timeoutMs: 30_000 }),

  /** space.get — record + drafts + roles with effective ceilings. */
  spaceGet: (spaceId) => call('space.get', { space_id: spaceId }, { timeoutMs: 30_000 }),

  /** space.archive — hide a space (archived spaces stay durable). */
  spaceArchive: (spaceId) => call('space.archive', { space_id: spaceId }, { timeoutMs: 30_000 }),

  /** space.attach_folder — import a folder IN PLACE via the workspace. */
  spaceAttachFolder: (spaceId, folder) =>
    call('space.attach_folder', { space_id: spaceId, folder }, { timeoutMs: 60_000 }),

  /** space.set_instruction — pasted text or a picked file path; the
   *  core scans it for prompt injection and quarantines suspicious docs. */
  spaceSetInstruction: (spaceId, { path, text } = {}) => {
    const params = { space_id: spaceId };
    if (text != null) params.text = text;
    if (path != null) params.path = path;
    return call('space.set_instruction', params, { timeoutMs: 60_000 });
  },

  /** space.propose_draft — a natural-language rule; nl_to_cron parses it. */
  spaceProposeDraft: (spaceId, rule) =>
    call('space.propose_draft', { space_id: spaceId, rule }, { timeoutMs: 30_000 }),

  /** space.approve_draft — your explicit approval of a pending rule. */
  spaceApproveDraft: (draftId) =>
    call('space.approve_draft', { draft_id: draftId }, { timeoutMs: 30_000 }),

  /** space.deny_draft — refuse a pending rule. */
  spaceDenyDraft: (draftId) =>
    call('space.deny_draft', { draft_id: draftId }, { timeoutMs: 30_000 }),

  // ---- live loop (arming approved drafts on the real scheduler) ------------
  /** liveloop.arm_draft — arm an APPROVED draft; every fire still needs
   *  approval (require_approval=true). Dangerous drafts never arm. */
  llArmDraft: (draftId) =>
    call('liveloop.arm_draft', { draft_id: draftId, approved: true }, { timeoutMs: 60_000 }),

  // ---- agent mode (goal + guarded shell + live status) --------------------
  /** workspace.agentmode_goal — objective + criteria; a rule-based evaluator
   *  checks them against the REAL workspace and says "unable" honestly. */
  amGoal: (objective, criteria) =>
    call('workspace.agentmode_goal', { objective, criteria }, { timeoutMs: 120_000 }),

  /** workspace.agentmode_report — re-evaluate a goal against the workspace. */
  amReport: (goalId) =>
    call('workspace.agentmode_report', { goal_id: goalId }, { timeoutMs: 120_000 }),

  /** workspace.agentmode_stop — cancel goals/subagents through engine tokens. */
  amStop: ({ goalId, planId, subagentId } = {}) => {
    const params = {};
    if (goalId) params.goal_id = goalId;
    if (planId) params.plan_id = planId;
    if (subagentId) params.subagent_id = subagentId;
    return call('workspace.agentmode_stop', params, { timeoutMs: 30_000 });
  },

  /** workspace.agentmode_status — live goals + subagent registry. */
  amStatus: () => call('workspace.agentmode_status', {}, { timeoutMs: 30_000 }),

  /** workspace.shell_propose — classify a command's risk (no execution). */
  shPropose: (command, cwd) =>
    call('workspace.shell_propose', cwd ? { command, cwd } : { command }, { timeoutMs: 30_000 }),

  /** workspace.shell_execute — run an approved command for real: network
   *  off, guarded commands confined to a registered root, dangerous
   *  commands never spawn even if approved. */
  shExecute: (approvalId) =>
    call(
      'workspace.shell_execute',
      { approval_id: approvalId, approved: true },
      { timeoutMs: 60_000 },
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

  // ---- real browser (SEC-03: approval-gated, quota, blocklist) ------------
  /** webbrowser.status — honest availability + controller state. */
  wbStatus: () => call('webbrowser.status', {}, { timeoutMs: 30_000 }),

  /** webbrowser.attach — CDP-attach to the user's Chrome (port 9222). */
  wbAttach: (port = 9222) => call('webbrowser.attach', { port }, { timeoutMs: 60_000 }),

  /** webbrowser.launch — fresh isolated visible Chrome (no user profile). */
  wbLaunch: () => call('webbrowser.launch', {}, { timeoutMs: 120_000 }),

  /** webbrowser.request — create a pending navigation approval. */
  wbRequest: (url, purpose) => call('webbrowser.request', { url, purpose }, { timeoutMs: 30_000 }),

  /** webbrowser.approve — single-use approval (expires per TTL). */
  wbApprove: (sessionId) =>
    call('webbrowser.approve', { session_id: sessionId }, { timeoutMs: 30_000 }),

  /** webbrowser.deny — refuse a pending navigation. */
  wbDeny: (sessionId) => call('webbrowser.deny', { session_id: sessionId }, { timeoutMs: 30_000 }),

  /** webbrowser.navigate — real navigation; approval_required comes back
   *  as a structured result with the pending session, never as a fake page. */
  wbNavigate: (url, purpose, timeout = 45) =>
    call('webbrowser.navigate', { url, purpose, timeout }, { timeoutMs: 180_000 }),

  /** webbrowser.content — re-extract the current page. */
  wbContent: () => call('webbrowser.content', {}, { timeoutMs: 60_000 }),

  /** webbrowser.click — click an element by CSS selector. */
  wbClick: (selector) => call('webbrowser.click', { selector }, { timeoutMs: 60_000 }),

  /** webbrowser.fill — type text into an element. */
  wbFill: (selector, value) => call('webbrowser.fill', { selector, value }, { timeoutMs: 60_000 }),

  /** webbrowser.screenshot — full-page screenshot to the local dir. */
  wbScreenshot: () => call('webbrowser.screenshot', {}, { timeoutMs: 60_000 }),

  /** webbrowser.close — end the session. */
  wbClose: () => call('webbrowser.close', {}, { timeoutMs: 30_000 }),

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

  /** dataqa.sessions.create — from a discovered dataset_id. */
  dataSessionFromDataset: (datasetId) =>
    call('dataqa.sessions.create', { dataset_id: datasetId }, { timeoutMs: 120_000 }),

  /** dataqa.sessions.list — loaded sessions. */
  dataSessionsList: () => call('dataqa.sessions.list', {}, { timeoutMs: 30_000 }),

  /** dataqa.sessions.get — full record incl. the last turns. */
  dataSessionGet: (sessionId) =>
    call('dataqa.sessions.get', { session_id: sessionId }, { timeoutMs: 60_000 }),

  /** dataqa.sessions.delete — remove a session and its chart assets. */
  dataSessionDelete: (sessionId) =>
    call('dataqa.sessions.delete', { session_id: sessionId }, { timeoutMs: 30_000 }),

  /** dataqa.discover — Persian-aware dataset discovery + bounded profiles. */
  dataDiscover: (query = '', limit = 20) =>
    call('dataqa.discover', { query, limit }, { timeoutMs: 120_000 }),

  /** dataqa.chart — the session's SVG, built only from executed evidence. */
  dataChart: (sessionId) => call('dataqa.chart', { session_id: sessionId }, { timeoutMs: 60_000 }),

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
