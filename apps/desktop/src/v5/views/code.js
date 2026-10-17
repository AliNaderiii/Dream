/**
 * Code — run real Python in the core's container sandbox (`sandbox.run_code`).
 *
 * The contract this view renders is `dream.security.codeexec`; the same shape
 * the backend validates. `status` is one of:
 *
 *   success     the program ran and exited 0
 *   error       the program ran and exited non-zero (or the runner failed)
 *   timeout     the backend's deadline fired and the container was terminated
 *   cancelled   the run was cancelled and the container was terminated
 *   denied      the request never reached a runner (bad field, oversized code,
 *               a workspace outside the sandbox root)
 *   unavailable that is `unavailable` and nothing ran on the host
 *
 * Nothing here is simulated: the panel shows what the core returned. When the
 * core cannot isolate, the view says so instead of printing a fabricated result.
 *
 * `variables_updated` is always empty on purpose — each run is a fresh
 * container, so there is no notebook-like namespace to carry state between
 * runs. The status strip says that in words rather than leaving the reader to
 * infer it from a zero.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

/** Persian label + chip class per contract status. Unknown values are shown raw. */
const STATUS = {
  success: { fa: 'موفق', cls: 'ok' },
  error: { fa: 'خطای برنامه', cls: 'err' },
  timeout: { fa: 'مهلت تمام شد', cls: 'warn' },
  cancelled: { fa: 'لغو شد', cls: 'warn' },
  denied: { fa: 'رد شد', cls: 'err' },
  unavailable: { fa: 'در دسترس نیست', cls: 'warn' },
};

const statusOf = (res) => String(res?.status ?? res?.result?.status ?? '');
const labelFor = (s) => STATUS[s] || { fa: s || 'نامشخص', cls: 'warn' };

/** One honest sentence about what the isolation profile actually is. */
function isolationLine(isolation) {
  if (!isolation || !isolation.backend) return null;
  const parts = [
    `بک‌اند: ${isolation.backend}`,
    `شبکه: ${isolation.network === 'none' ? 'خاموش' : isolation.network}`,
    `ریشهٔ فایل‌سیستم: ${isolation.rootfs === 'read-only' ? 'فقط‌خواندنی' : isolation.rootfs}`,
    `ظرفیت‌ها: ${isolation.capabilities === 'drop-all' ? 'حذف‌شده' : isolation.capabilities}`,
    `کاربر: ${isolation.user}`,
  ];
  return parts.join(' • ');
}

export function codeView(root, ctx) {
  let result = null; // the sandbox.run_code envelope
  let status = null; // sandbox.get_status
  let busy = false;
  let error = null;
  let liveId = null; // execution_id of the in-flight run, for cancel

  const editor = h('textarea', {
    class: 'input code-editor',
    dir: 'ltr',
    rows: 10,
    spellcheck: 'false',
    placeholder:
      'print("سلام از سندباکس دریم")\n\n# هر اجرا یک کانتینر تازه است — شبکه خاموش و ریشهٔ فایل‌سیستم فقط‌خواندنی',
  });
  const stage = h('div', { class: 'code-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) {
      children.push(
        h(
          'div',
          { class: 'notice' },
          h('span', { html: ic('refresh') }),
          'در حال اجرا…',
          liveId
            ? h(
                'button',
                { class: 'btn btn-sm', onclick: cancelRun },
                h('span', { html: ic('x') }),
                'لغو',
              )
            : null,
        ),
      );
    }

    if (result) {
      const s = statusOf(result);
      const info = labelFor(s);
      const detail = result.result || {};
      const ok = s === 'success';
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'OUTPUT' }),
          h(
            'div',
            { class: 'result-meta' },
            h('span', { class: `chip ${info.cls}` }, h('span', { class: 'dot' }), info.fa),
            detail.duration_ms != null
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${Math.round(detail.duration_ms)}ms`,
                )
              : null,
            detail.exit_code != null && detail.exit_code >= 0
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `exit ${detail.exit_code}`,
                )
              : null,
            detail.truncated
              ? h('span', { class: 'chip warn' }, h('span', { class: 'dot' }), 'خروجی بریده شد')
              : null,
            result.execution_id
              ? h('span', { class: 'chip mono', title: result.execution_id, text: 'شناسه اجرا' })
              : null,
            h(
              'button',
              {
                class: 'btn btn-sm evidence-link',
                onclick: () =>
                  ctx.openEvidence({
                    title: 'اجرای کد',
                    steps: [
                      {
                        name: 'sandbox.run_code',
                        detail: `اجرای واقعی پایتون در ${detail.isolation?.backend || 'داخل کانتینر'}`,
                        meta: detail.isolation?.network === 'none' ? 'شبکه خاموش' : 'هسته',
                      },
                      {
                        name: 'خروجی',
                        detail: `${(detail.stdout || '').length} نویسه stdout`,
                        meta: ok ? 'موفق' : info.fa,
                      },
                    ],
                  }),
              },
              h('span', { html: ic('evidence') }),
              'شواهد',
            ),
          ),
          detail.stdout ? h('pre', { class: 'files-preview-text' }, detail.stdout) : null,
          detail.stderr
            ? h('pre', { class: 'files-preview-text code-stderr' }, detail.stderr)
            : null,
          detail.error_message ? notice(detail.error_message, ok ? 'ok' : 'err') : null,
          detail.truncated && detail.stdout_path
            ? h('span', { class: 'micro mono', text: `خروجی کامل: ${detail.stdout_path}` })
            : null,
          isolationLine(detail.isolation)
            ? h('span', { class: 'micro', text: isolationLine(detail.isolation) })
            : null,
        ),
      );

      const arts = detail.artifacts || [];
      if (arts.length) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'ARTIFACTS' }),
            ...arts.map((a) =>
              h(
                'div',
                { class: 'files-row' },
                h('span', { class: 'files-row-ic', html: ic('file') }),
                h(
                  'div',
                  { class: 'files-row-main' },
                  h('span', { class: 'files-row-name', text: a.name || a.file_path }),
                  h('span', { class: 'files-row-meta mono', text: a.file_path }),
                ),
                h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  a.size_bytes != null ? fmtBytes(a.size_bytes) : '—',
                ),
              ),
            ),
          ),
        );
      }
    }

    if (status) {
      children.push(
        h(
          'div',
          { class: 'result-meta' },
          h(
            'span',
            { class: `chip ${status.available ? 'ok' : 'warn'}` },
            h('span', { class: 'dot' }),
            status.available ? `بک‌اند: ${status.backend || 'docker'}` : 'بک‌اند در دسترس نیست',
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `اجراها: ${status.total_executions ?? 0}`,
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `آرتیفکت‌ها: ${status.total_artifacts ?? 0}`,
          ),
          status.statefulness
            ? h('span', {
                class: 'chip',
                title: status.statefulness,
                text: 'بدون وضعیت بین‌اجرایی',
              })
            : null,
        ),
      );
    }
    stage.replaceChildren(...children);
  }

  async function run() {
    const code = editor.value.trim();
    if (!code || busy) return;
    busy = true;
    error = null;
    result = null;
    liveId = null;
    renderStage();
    try {
      const res = await api.sandboxRun(code);
      result = res;
      liveId = res?.execution_id || res?.result?.execution_id || null;
      const s = statusOf(res);
      // `denied`, `unavailable` and `timeout` all carry a bilingual
      // `error_message`; surfacing it is the point of the contract.
      if (s !== 'success' && res?.result?.error_message) {
        error = res.result.error_message;
      }
    } catch (e) {
      error = msg(e);
    } finally {
      busy = false;
      liveId = null;
      renderStage();
      refreshStatus();
    }
  }

  async function cancelRun() {
    const id = liveId || result?.execution_id;
    if (!id) return;
    try {
      await api.sandboxCancel(id);
    } catch (e) {
      error = msg(e);
    }
  }

  async function refreshStatus() {
    try {
      status = await api.sandboxStatus();
    } catch (e) {
      status = null;
      error = msg(e); // honest: in the browser preview there is no core sandbox
    }
    renderStage();
  }

  async function reset() {
    try {
      await api.sandboxReset();
      result = null;
      error = null;
      await refreshStatus();
    } catch (e) {
      error = msg(e);
      renderStage();
    }
  }

  root.append(
    h(
      'div',
      { class: 'code-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        h(
          'button',
          { class: 'btn btn-primary', disabled: busy, onclick: run },
          h('span', { html: ic('terminal') }),
          'اجرا',
        ),
        h(
          'button',
          { class: 'btn', onclick: reset },
          h('span', { html: ic('refresh') }),
          'بازنشانی نشست',
        ),
      ),
      h(
        'span',
        { class: 'chip warn' },
        h('span', { class: 'dot' }),
        'اجرای واقعی پایتون فقط داخل کانتینر: شبکه خاموش، ریشهٔ فایل‌سیستم فقط‌خواندنی، فقط پوشهٔ اجرا نوشتنی — بدون داکر اجرا نمی‌شود',
      ),
      editor,
      stage,
    ),
  );

  renderStage();
  refreshStatus();
}
