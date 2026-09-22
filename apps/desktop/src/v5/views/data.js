/**
 * Data tool — dataset → question → grounded answer with an evidence table
 * and KPI cards. Fully wired: dataqa.sessions.create + dataqa.ask.
 * The answer never floats free of its evidence (DeepAnalyze habit).
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function dataView(root, ctx) {
  let session = null; // {session_id, dataset, turn_count}
  let lastAnswer = null; // DataQaAskResult.final_answer

  const sessionHost = h('div', { class: 'data-datasets' });
  const answer = h('div', { class: 'data-answer' });
  const questionInput = h('input', {
    class: 'input data-question',
    placeholder: 'مثلاً: پرفروش‌ترین محصول هر ماه کدام بوده؟',
    onkeydown: (e) => {
      if (e.key === 'Enter') ask();
    },
  });
  const askBtn = h(
    'button',
    { class: 'btn btn-primary', onclick: ask },
    h('span', { html: ic('send') }),
    'بپرس',
  );
  const loadBtn = h(
    'button',
    {
      class: 'btn',
      onclick: loadDataset,
    },
    h('span', { html: ic('upload') }),
    'بارگذاری مجموعه‌داده',
  );

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic('alert') }, text);
  }

  function renderSession({ busy = '', error = null } = {}) {
    const children = [];
    if (session) {
      const ds = session.dataset ?? {};
      children.push(
        h(
          'div',
          { class: 'data-session card' },
          h('span', { class: 'data-session-ic', html: ic('db') }),
          h(
            'div',
            { class: 'data-session-main' },
            h('span', {
              class: 'data-session-name',
              text: ds.dataset_id || ds.label || 'مجموعه‌داده',
            }),
            h('span', {
              class: 'data-session-meta mono',
              text: `${ds.row_count ?? '—'} ردیف · ${ds.format ?? ''} · نشست ${session.session_id.slice(0, 8)}`,
            }),
          ),
          h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), 'بارگذاری شد'),
        ),
      );
    } else {
      children.push(
        h(
          'span',
          { class: 'empty empty-sm' },
          h('span', { html: ic('db') }),
          h('span', { class: 'empty-title', text: 'مجموعه‌داده‌ای بارگذاری نشده' }),
          h('span', {
            class: 'empty-note',
            text: 'CSV / JSON / SQLite — مسیر واقعی از طریق گفت‌وگوی فایل سیستم.',
          }),
        ),
      );
    }
    if (busy)
      children.push(
        h(
          'div',
          { class: 'notice', html: ic('refresh') },
          busy === 'load' ? 'در حال بارگذاری و پروفایل‌سازی…' : 'در حال تحلیل پرسش…',
        ),
      );
    if (error) children.push(notice(error));
    sessionHost.replaceChildren(...children);
    askBtn.disabled = !!busy || !session;
    loadBtn.disabled = !!busy;
  }

  function renderAnswer() {
    if (!lastAnswer) {
      answer.replaceChildren(
        h(
          'div',
          { class: 'empty' },
          h('span', { html: ic('chart') }),
          h('span', { class: 'empty-title', text: 'هنوز پرسشی پاسخ نگرفته' }),
          h('span', {
            class: 'empty-note',
            text: 'مجموعه‌داده را بارگذاری کنید و بپرسید؛ پاسخ همراه جدول شواهد و کد تحلیل نمایش داده می‌شود.',
          }),
        ),
      );
      return;
    }
    const fa = lastAnswer;
    const ev = fa.evidence ?? {};
    const children = [
      h(
        'div',
        { class: 'result-panel card' },
        h('span', { class: 'micro', text: 'ANSWER' }),
        h('div', { class: 'result-text', text: fa.answer || '—' }),
        h(
          'div',
          { class: 'result-meta' },
          h(
            'span',
            { class: `chip ${fa.grounded ? 'ok' : 'warn'}` },
            h('span', { class: 'dot' }),
            fa.grounded ? 'مستند به داده' : 'بدون پشتوانه کامل',
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `${ev.rows_considered ?? '—'} ردیف بررسی شد`,
          ),
          fa.status !== 'ok'
            ? h('span', { class: 'chip warn' }, h('span', { class: 'dot' }), fa.status)
            : null,
        ),
      ),
    ];
    const rows = Array.isArray(ev.rows) ? ev.rows : [];
    const columns =
      Array.isArray(ev.columns) && ev.columns.length
        ? ev.columns
        : rows[0]
          ? Object.keys(rows[0])
          : [];
    if (columns.length && rows.length) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'EVIDENCE' }),
          h(
            'div',
            { class: 'table-scroll' },
            h(
              'table',
              { class: 'evidence-table' },
              h('thead', h('tr', ...columns.map((c) => h('th', { text: c })))),
              h(
                'tbody',
                ...rows
                  .slice(0, 12)
                  .map((r) =>
                    h(
                      'tr',
                      ...columns.map((c) =>
                        h('td', { text: r[c] === undefined || r[c] === null ? '—' : String(r[c]) }),
                      ),
                    ),
                  ),
              ),
            ),
            rows.length > 12
              ? h('span', { class: 'faint', text: `… و ${rows.length - 12} ردیف دیگر` })
              : null,
          ),
        ),
      );
    }
    children.push(
      h(
        'button',
        {
          class: 'btn btn-sm evidence-link',
          onclick: () =>
            ctx.openEvidence({
              title: 'پاسخ تحلیل داده',
              steps: [
                {
                  name: 'مجموعه‌داده',
                  detail: session?.dataset?.dataset_id || '—',
                  meta: `${session?.dataset?.row_count ?? '—'} ردیف`,
                },
                { name: 'پرسش', detail: questionInput.value || '—' },
                {
                  name: 'sandbox.analyze_data',
                  detail: fa.generated_code ? `${fa.generated_code.split('\n').length} خط کد` : '—',
                  meta: fa.sandbox?.kind ?? 'هسته',
                },
                {
                  name: 'پاسخ نهایی',
                  detail: `وضعیت: ${fa.status}`,
                  meta: `${ev.rows_considered ?? '—'} ردیف`,
                },
              ],
            }),
        },
        h('span', { html: ic('evidence') }),
        'زنجیره شواهد و کد تحلیل',
      ),
    );
    answer.replaceChildren(...children);
  }

  async function loadDataset() {
    renderSession({ busy: 'load' });
    try {
      const entry = await pickFile('انتخاب مجموعه‌داده (CSV / JSON / SQLite)');
      if (!entry) {
        renderSession();
        return;
      }
      session = await api.dataSessionCreate(entry.path);
      lastAnswer = null;
      renderSession();
      renderAnswer();
    } catch (e) {
      renderSession({ error: msg(e) });
    }
  }

  async function ask() {
    const q = questionInput.value.trim();
    if (!q || !session) return;
    renderSession({ busy: 'ask' });
    try {
      const res = await api.dataAsk(session.session_id, q);
      lastAnswer = res?.final_answer ?? null;
      session = { ...session, turn_count: (session.turn_count ?? 0) + 1 };
      renderSession();
      renderAnswer();
    } catch (e) {
      renderSession({ error: msg(e) });
    }
  }

  root.append(
    h(
      'div',
      { class: 'data-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h('div', { class: 'data-ask-row' }, questionInput, askBtn),
        h(
          'div',
          { class: 'data-ask-meta' },
          loadBtn,
          h('span', {
            class: 'faint data-hint',
            text: 'پاسخ‌ها فقط از داده واقعی استخراج می‌شوند و کد تحلیلشان قابل بازبینی است.',
          }),
        ),
      ),
      sessionHost,
      answer,
    ),
  );

  renderSession();
  renderAnswer();
}
