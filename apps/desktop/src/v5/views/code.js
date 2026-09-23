/**
 * Code — run real Python in the core's sandbox (sandbox.run_code): a stateful
 * namespace, captured stdout/stderr, artifacts, and a security blocklist.
 * What you see is what the interpreter printed — no simulation.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function codeView(root, ctx) {
  let result = null; // run_code result
  let status = null; // sandbox.get_status
  let busy = false;
  let error = null;

  const editor = h('textarea', {
    class: 'input code-editor',
    dir: 'ltr',
    rows: 10,
    spellcheck: 'false',
    placeholder:
      'print("سلام از سندباکس دریم")\n\n# namespace حالت‌دار است — متغیرها بین اجراها می‌مانند',
  });
  const stage = h('div', { class: 'code-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, 'در حال اجرا…'));

    if (result) {
      const ok = String(result.status || result.result?.status || '') === 'success';
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'OUTPUT' }),
          h(
            'div',
            { class: 'result-meta' },
            h(
              'span',
              { class: `chip ${ok ? 'ok' : 'err'}` },
              h('span', { class: 'dot' }),
              ok ? 'موفق' : 'خطا',
            ),
            result.result?.duration_ms != null
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${Math.round(result.result.duration_ms)}ms`,
                )
              : null,
            result.result?.variables_updated?.length
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${result.result.variables_updated.length} متغیر`,
                )
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
                        detail: 'اجرای واقعی پایتون',
                        meta: 'هسته پایتون',
                      },
                      {
                        name: 'خروجی',
                        detail: `${(result.result?.stdout || '').length} نویسه stdout`,
                        meta: ok ? 'موفق' : 'با خطا',
                      },
                    ],
                  }),
              },
              h('span', { html: ic('evidence') }),
              'شواهد',
            ),
          ),
          result.result?.stdout
            ? h('pre', { class: 'files-preview-text' }, result.result.stdout)
            : null,
          result.result?.stderr
            ? h('pre', { class: 'files-preview-text code-stderr' }, result.result.stderr)
            : null,
          result.result?.error_message ? notice(result.result.error_message) : null,
        ),
      );
      const arts = result.result?.artifacts || [];
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
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `اجراها: ${status.total_executions ?? 0}`,
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `متغیرها: ${status.variables_count ?? 0}`,
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `آرتیفکت‌ها: ${status.total_artifacts ?? 0}`,
          ),
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
    renderStage();
    try {
      const res = await api.sandboxRun(code);
      if (res?.status && res.status !== 'success' && res.result?.error_message) {
        error = res.result.error_message;
      }
      result = res;
    } catch (e) {
      error = msg(e);
    } finally {
      busy = false;
      renderStage();
      refreshStatus();
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
        'اجرای واقعی پایتون در سندباکس هسته — با بلاک‌لیست امنیتی و مهلت ۱۵ ثانیه',
      ),
      editor,
      stage,
    ),
  );

  renderStage();
  refreshStatus();
}
