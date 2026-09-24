/**
 * Data studio — dataset → question → grounded answer with an evidence table,
 * KPI cards, a REAL SVG chart built only from executed evidence, Persian-aware
 * dataset discovery over the Dream workspace, and saved-session management.
 * Fully wired: dataqa.sessions.create/list/get/delete + dataqa.discover +
 * dataqa.ask + dataqa.chart. The answer never floats free of its evidence
 * (DeepAnalyze habit), and a chart appears only when the executed result
 * supports one — the core refuses otherwise, honestly.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const when = (stamp) => (stamp ? new Date(Number(stamp) * 1000).toLocaleString('fa-IR') : '—');

export function dataView(root, ctx) {
  let session = null; // public session record {session_id, dataset, profile, turn_count}
  let lastAnswer = null; // DataQaAskResult.final_answer
  let candidates = []; // dataqa.discover results
  let savedSessions = []; // dataqa.sessions.list summaries
  let chart = null; // {kind, title, svg, ...}

  const statusHost = h('div', { class: 'data-status' });
  let error = null;
  let busy = '';

  function renderStatus() {
    const rows = [];
    if (error) rows.push(h('div', { class: 'notice err', html: ic('alert') }, error));
    if (busy) rows.push(h('div', { class: 'notice', html: ic('refresh') }, busy));
    statusHost.replaceChildren(...rows);
  }

  const sessionHost = h('div', { class: 'data-datasets' });
  const answer = h('div', { class: 'data-answer' });
  const discoverHost = h('div', { class: 'data-discover-results' });
  const sessionsHost = h('div', { class: 'data-saved-sessions' });

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

  const discoverInput = h('input', {
    class: 'input data-discover-q',
    placeholder: 'کشف در فضای کاری — مثلاً: فروش، مشتری، موجودی…',
    onkeydown: (e) => {
      if (e.key === 'Enter') discover();
    },
  });
  const discoverBtn = h(
    'button',
    { class: 'btn', onclick: discover },
    h('span', { html: ic('search') }),
    'کشف',
  );

  function renderSession() {
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
              text: ds.name || ds.dataset_id || 'مجموعه‌داده',
            }),
            h('span', {
              class: 'data-session-meta mono',
              text: `${ds.row_count ?? '—'} ردیف · ${ds.format ?? ''} · ${session.turn_count ?? 0} پرسش · نشست ${session.session_id.slice(0, 8)}`,
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
            text: 'CSV / JSON / SQLite — از طریق کشف فضای کاری یا انتخاب فایل.',
          }),
        ),
      );
    }
    sessionHost.replaceChildren(...children);
    askBtn.disabled = !session;
    loadBtn.disabled = !!busy;
  }

  function candidateCard(c) {
    const cols = Array.isArray(c.columns) ? c.columns.slice(0, 6) : [];
    return h(
      'div',
      { class: 'disc-candidate card' },
      h(
        'div',
        { class: 'disc-head' },
        h('span', { class: 'disc-name', text: c.name || c.dataset_id || '—' }),
        h(
          'span',
          { class: 'chip' },
          h('span', { class: 'dot' }),
          String(c.format || '—').toUpperCase(),
        ),
        c.loadable
          ? h(
              'span',
              { class: 'chip ok' },
              h('span', { class: 'dot' }),
              `${c.row_count ?? '—'} ردیف`,
            )
          : h('span', { class: 'chip err' }, h('span', { class: 'dot' }), 'قابل بارگذاری نیست'),
      ),
      cols.length
        ? h(
            'div',
            { class: 'disc-cols' },
            ...cols.map((col) => h('span', { class: 'chip faint-chip', text: col })),
          )
        : null,
      Array.isArray(c.reasons) && c.reasons.length
        ? h('span', { class: 'muted disc-reasons', text: c.reasons.join(' · ') })
        : null,
      c.limitation
        ? h('span', { class: 'muted disc-reasons', text: `محدودیت: ${c.limitation}` })
        : null,
      c.loadable
        ? h(
            'div',
            { class: 'settings-actions' },
            h(
              'button',
              {
                class: 'btn btn-sm btn-primary',
                onclick: () => createFromCandidate(c),
              },
              h('span', { html: ic('plus') }),
              'شروع نشست',
            ),
          )
        : null,
    );
  }

  function renderDiscover() {
    if (candidates.length === 0) {
      discoverHost.replaceChildren(
        h('span', {
          class: 'muted',
          text: 'کشف، فضای کاری دریم (DREAM_WORKSPACE_ROOT یا پوشهٔ کاری هسته) را با مترادف‌های فارسی/انگلیسی جستجو می‌کند و ساختار مجموعه‌داده‌ها را مقید پروفایل می‌کند.',
        }),
      );
      return;
    }
    discoverHost.replaceChildren(...candidates.map(candidateCard));
  }

  function sessionRow(row) {
    const ds = row.dataset ?? {};
    const active = session && session.session_id === row.session_id;
    return h(
      'div',
      { class: `saved-row${active ? ' active' : ''}` },
      h(
        'div',
        { class: 'saved-main' },
        h('span', { class: 'saved-name', text: ds.name || ds.dataset_id || '—' }),
        h('span', {
          class: 'muted saved-meta mono',
          text: `${ds.row_count ?? '—'} ردیف · ${row.turn_count ?? 0} پرسش · ${when(row.updated_at)}`,
        }),
      ),
      h(
        'div',
        { class: 'saved-actions' },
        h(
          'button',
          {
            class: 'btn btn-sm',
            onclick: () => openSession(row.session_id),
          },
          'بازکردن',
        ),
        h(
          'button',
          {
            class: 'btn btn-sm',
            onclick: () => deleteSession(row.session_id),
          },
          'حذف',
        ),
      ),
    );
  }

  function renderSessions() {
    if (savedSessions.length === 0) {
      sessionsHost.replaceChildren(
        h('span', { class: 'muted', text: 'نشست ذخیره‌شده‌ای نیست — هر تحلیل، ماندگار است.' }),
      );
      return;
    }
    sessionsHost.replaceChildren(...savedSessions.map(sessionRow));
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
            text: 'مجموعه‌داده را بارگذاری کنید و بپرسید؛ پاسخ همراه جدول شواهد، کد تحلیل و — اگر داده پشتیبانی کند — نمودار نمایش داده می‌شود.',
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
          h(
            'button',
            {
              class: 'btn btn-sm evidence-link',
              onclick: loadChart,
              title: 'نمودار فقط وقتی ساخته می‌شود که نتیجهٔ اجراشده از آن پشتیبانی کند',
            },
            h('span', { html: ic('chart') }),
            'نمودار',
          ),
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
    if (chart?.svg) {
      children.push(
        h(
          'div',
          { class: 'result-panel card chart-panel' },
          h('span', { class: 'micro', text: 'CHART' }),
          h('span', { class: 'chart-title', text: chart.title || '—' }),
          h('div', { class: 'chart-svg', html: chart.svg }),
          h(
            'button',
            {
              class: 'btn btn-ghost btn-sm evidence-link',
              onclick: () =>
                ctx.openEvidence({
                  title: 'نمودار از شواهد اجراشده',
                  steps: [
                    { name: 'مجموعه‌داده', detail: session?.dataset?.dataset_id || '—' },
                    { name: 'نوع نمودار', detail: chart.kind || '—', meta: chart.title || '' },
                    {
                      name: 'dataqa.chart',
                      detail: 'SVG فقط از ردیف‌های واقعی اجراشده ساخته شد',
                      meta: `${chart.x || ''} → ${chart.y || ''}`,
                    },
                  ],
                }),
            },
            h('span', { html: ic('evidence') }),
            'شواهد نمودار',
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

  // ── actions ──────────────────────────────────────────────────────────────
  async function discover() {
    busy = 'در حال کشف مجموعه‌داده‌ها در فضای کاری…';
    error = null;
    renderStatus();
    try {
      const res = await api.dataDiscover(discoverInput.value.trim());
      candidates = res?.candidates || [];
      renderDiscover();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function createFromCandidate(c) {
    busy = `در حال ساخت نشست از «${c.name || c.dataset_id}»…`;
    error = null;
    renderStatus();
    try {
      session = await api.dataSessionFromDataset(c.dataset_id);
      lastAnswer = null;
      chart = null;
      renderSession();
      renderAnswer();
      await refreshSessions();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function refreshSessions() {
    try {
      const res = await api.dataSessionsList();
      savedSessions = res?.sessions || [];
    } catch {
      savedSessions = [];
    }
    renderSessions();
  }

  async function openSession(sessionId) {
    busy = 'در حال بازکردن نشست…';
    error = null;
    renderStatus();
    try {
      const res = await api.dataSessionGet(sessionId);
      session = res;
      const turns = Array.isArray(res?.turns) ? res.turns : [];
      lastAnswer = turns.length ? (turns[turns.length - 1].final_answer ?? null) : null;
      chart = null;
      renderSession();
      renderAnswer();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function deleteSession(sessionId) {
    busy = 'در حال حذف نشست…';
    error = null;
    renderStatus();
    try {
      await api.dataSessionDelete(sessionId);
      if (session?.session_id === sessionId) {
        session = null;
        lastAnswer = null;
        chart = null;
        renderSession();
        renderAnswer();
      }
      await refreshSessions();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function loadChart() {
    busy = 'در حال ساخت نمودار از نتیجهٔ اجراشده…';
    error = null;
    renderStatus();
    try {
      const res = await api.dataChart(session.session_id);
      chart = res?.chart || null;
      renderAnswer();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function loadDataset() {
    busy = 'در حال بارگذاری و پروفایل‌سازی…';
    error = null;
    renderStatus();
    renderSession();
    try {
      const entry = await pickFile('انتخاب مجموعه‌داده (CSV / JSON / SQLite)');
      if (!entry) {
        busy = '';
        renderStatus();
        return;
      }
      session = await api.dataSessionCreate(entry.path);
      lastAnswer = null;
      chart = null;
      renderSession();
      renderAnswer();
      await refreshSessions();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function ask() {
    const q = questionInput.value.trim();
    if (!q || !session) return;
    busy = 'در حال تحلیل پرسش…';
    error = null;
    renderStatus();
    renderSession();
    try {
      const res = await api.dataAsk(session.session_id, q);
      lastAnswer = res?.final_answer ?? null;
      chart = null;
      session = { ...session, turn_count: (session.turn_count ?? 0) + 1 };
      renderSession();
      renderAnswer();
      refreshSessions();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  // ── layout ───────────────────────────────────────────────────────────────
  root.append(
    h(
      'div',
      { class: 'data-view' },
      statusHost,
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
      section(
        'DISCOVER',
        'کشف مجموعه‌داده در فضای کاری',
        h(
          'div',
          { class: 'section-card card' },
          h('div', { class: 'data-ask-row' }, discoverInput, discoverBtn),
          discoverHost,
        ),
      ),
      section(
        'SESSIONS',
        'نشست‌های ذخیره‌شده',
        h('div', { class: 'section-card card' }, sessionsHost),
      ),
    ),
  );

  renderSession();
  renderAnswer();
  renderDiscover();
  renderSessions();
  refreshSessions();
}

function section(micro, title, ...children) {
  return h(
    'section',
    { class: 'rt-section' },
    h(
      'div',
      { class: 'rt-section-head' },
      h('span', { class: 'micro', text: micro }),
      h('span', { class: 'rt-section-title', text: title }),
    ),
    ...children,
  );
}
