/**
 * Research — deep research projects, fully wired:
 * research.create → plan (APPROVAL_PENDING) → approve → report.
 * The Open-Science habit: nothing runs past the plan without your approval.
 */

import { h, fmtTime } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFolder, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const PIPELINE = [
  { name: 'برنامه', note: 'ایجنت منابع و مراحل را پیشنهاد می‌دهد' },
  { name: 'منابع', note: 'جست‌وجو و مرور وب واقعی' },
  { name: 'پیش‌نویس', note: 'نوشتن با استناد به منابع' },
  { name: 'تأیید', note: 'شما پیش از خروجی نهایی تأیید می‌کنید' },
  { name: 'خروجی', note: 'گزارش PDF فارسی با پیوند به شواهد' },
];

export function researchView(root, ctx) {
  let session = null; // summary {session_id, topic, phase/status...}
  let record = null; // research.get full record

  const topicInput = h('input', {
    class: 'input data-question',
    placeholder: 'موضوع پژوهش… مثلاً: مقایسه فناوری‌های ذخیره‌سازی خورشیدی در ایران',
  });
  const startBtn = h(
    'button',
    { class: 'btn btn-primary', onclick: start },
    h('span', { html: ic('search') }),
    'شروع پژوهش',
  );
  const modifyInput = h('textarea', {
    class: 'input research-modify-input',
    rows: 3,
    placeholder: '{"objective":"..."} یا {"sections":[{"title":"..."}]}',
  });
  const stage = h('div', { class: 'research-stage' });
  let busy = false;

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic('alert') }, text);
  }

  function phaseChip(phase) {
    const p = String(phase ?? 'unknown');
    const cls = /pending/i.test(p) ? 'warn' : /complete|done/i.test(p) ? 'ok' : '';
    return h('span', { class: `chip ${cls}` }, h('span', { class: 'dot' }), `مرحله: ${p}`);
  }

  async function refresh() {
    if (!session?.session_id) return;
    try {
      record = await api.researchGet(session.session_id);
      session = { ...session, ...record };
      renderStage();
    } catch {
      /* summary-only display is fine */
    }
  }

  function planSteps() {
    const plan = record?.plan ?? session?.plan;
    const steps = plan?.steps ?? plan?.outline ?? [];
    if (!Array.isArray(steps) || steps.length === 0) return null;
    return h(
      'div',
      { class: 'result-panel card' },
      h('span', { class: 'micro', text: 'PLAN — نیازمند تأیید شما' }),
      ...steps.map((s, i) => {
        const label =
          typeof s === 'string' ? s : (s.title ?? s.name ?? s.description ?? JSON.stringify(s));
        return h(
          'div',
          { class: 'log-row' },
          h('span', { class: 'evidence-idx mono', text: String(i + 1).padStart(2, '0') }),
          h('span', { class: 'log-detail', text: label }),
          typeof s === 'object' && s.status
            ? h('span', { class: 'chip' }, h('span', { class: 'dot' }), String(s.status))
            : null,
        );
      }),
    );
  }

  function renderStage({ error = null, busyLabel = '' } = {}) {
    if (!session) {
      stage.replaceChildren(
        h(
          'div',
          { class: 'empty' },
          h('span', { html: ic('search') }),
          h('span', { class: 'empty-title', text: 'پروژه پژوهشی ندارید' }),
          h('span', {
            class: 'empty-note',
            text: 'موضوع را بنویسید، پوشه خروجی را انتخاب کنید و شروع بزنید — برنامه پیشنهادی پیش از اجرا به تأیید شما می‌رسد.',
          }),
        ),
      );
      return;
    }
    const children = [
      h(
        'div',
        { class: 'doc-file card' },
        h('span', { class: 'doc-file-ic', html: ic('search') }),
        h(
          'div',
          { class: 'doc-file-main' },
          h('span', { class: 'doc-file-name', text: session.topic ?? 'پژوهش' }),
          h('span', {
            class: 'doc-file-meta mono',
            text: `نشست ${String(session.session_id).slice(0, 8)}`,
          }),
        ),
      ),
      h(
        'div',
        { class: 'result-meta' },
        phaseChip(session.phase ?? session.status),
        session.workspace
          ? h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'پوشه خروجی انتخاب شد')
          : null,
      ),
    ];
    if (runEvidence && !busy) {
      children.push(
        h(
          'button',
          {
            class: 'btn btn-sm evidence-link',
            onclick: () => ctx.openEvidence(runEvidence),
          },
          h('span', { html: ic('evidence') }),
          'شواهد اجرا',
        ),
      );
    }
    if (busyLabel) children.push(h('div', { class: 'notice', html: ic('refresh') }, busyLabel));
    if (error) children.push(notice(error));
    const steps = planSteps();
    if (steps) children.push(steps);

    const phase = String(session.phase ?? session.status ?? '');
    if (!busy && /pending/i.test(phase)) {
      children.push(
        h(
          'div',
          { class: 'section-card card research-modify' },
          h('span', { class: 'micro', text: 'EDIT PLAN — JSON EXPLICIT' }),
          h('span', {
            class: 'muted',
            text: 'ویرایش فقط پس از ورود صریح شما اعمال می‌شود؛ برای برنامه‌ریزی مجدد از {"replan":true} استفاده کنید.',
          }),
          modifyInput,
          h('button', { class: 'btn btn-sm', onclick: modifyPlan }, 'اعمال اصلاح برنامه'),
        ),
        h(
          'div',
          { class: 'doc-actions' },
          h(
            'button',
            { class: 'btn btn-primary', onclick: approve },
            h('span', { html: ic('check') }),
            'تأیید برنامه و اجرا',
          ),
          h(
            'button',
            { class: 'btn', onclick: replan },
            h('span', { html: ic('refresh') }),
            'برنامه‌ریزی مجدد',
          ),
        ),
      );
    }
    if (!busy && !/pending/i.test(phase)) {
      children.push(
        h(
          'div',
          { class: 'doc-actions' },
          h(
            'button',
            { class: 'btn', onclick: refresh },
            h('span', { html: ic('refresh') }),
            'به‌روزرسانی وضعیت',
          ),
        ),
      );
    }
    const report = record?.report ?? session?.report;
    if (report) {
      const text =
        typeof report === 'string'
          ? report
          : (report.summary ?? JSON.stringify(report).slice(0, 400));
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'REPORT' }),
          h('div', { class: 'result-text', text }),
          h(
            'button',
            { class: 'btn btn-sm', disabled: !!busy, onclick: exportReport },
            'انتشار گزارش مستند',
          ),
          exportResult
            ? h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), 'گزارش در هسته منتشر شد')
            : null,
        ),
      );
    }
    const events = record?.events ?? [];
    if (Array.isArray(events) && events.length) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'EVENTS' }),
          ...events
            .slice(-10)
            .reverse()
            .map((ev) =>
              h(
                'div',
                { class: 'log-row' },
                h('span', { class: 'log-time mono', text: ev.ts ? fmtTime(ev.ts * 1000) : '—' }),
                h('span', { class: 'log-kind', text: ev.kind ?? ev.type ?? 'رویداد' }),
                h('span', { class: 'log-detail muted', text: ev.detail ?? ev.message ?? '—' }),
              ),
            ),
        ),
      );
    }
    stage.replaceChildren(...children);
  }

  async function start() {
    const topic = topicInput.value.trim();
    if (!topic || busy) return;
    if (!session?.workspace) {
      try {
        const folder = await pickFolder('پوشه خروجی پژوهش (گزارش و یافته‌ها)');
        if (!folder) return;
        session = { workspace: folder };
      } catch (e) {
        renderStage({ error: msg(e) });
        return;
      }
    }
    busy = true;
    startBtn.disabled = true;
    renderStage({ busyLabel: 'در حال ساخت نشست و برنامه‌ریزی…' });
    try {
      const created = await api.researchCreate(topic, session.workspace);
      session = { ...session, ...created, workspace: session.workspace };
      const planned = await api.researchPlan(session.session_id);
      session = { ...session, ...planned, topic };
      await refresh();
    } catch (e) {
      renderStage({ error: msg(e) });
    } finally {
      busy = false;
      startBtn.disabled = false;
    }
  }

  let runEvidence = null; // shown on demand — the drawer never opens itself
  let exportResult = null;

  async function modifyPlan() {
    let changes;
    try {
      changes = JSON.parse(modifyInput.value.trim());
    } catch {
      renderStage({ error: 'اصلاح برنامه باید JSON معتبر باشد.' });
      return;
    }
    busy = true;
    renderStage({ busyLabel: 'در حال اعمال اصلاح صریح روی برنامه…' });
    try {
      const modified = await api.researchModify(session.session_id, changes);
      session = { ...session, ...modified };
      await refresh();
    } catch (e) {
      renderStage({ error: msg(e) });
    } finally {
      busy = false;
    }
  }

  async function exportReport() {
    busy = true;
    renderStage({ busyLabel: 'در حال انتشار گزارش کامل در هسته…' });
    try {
      exportResult = await api.researchExport(session.session_id);
      await refresh();
    } catch (e) {
      renderStage({ error: msg(e) });
    } finally {
      busy = false;
    }
  }

  async function approve() {
    busy = true;
    renderStage({
      busyLabel: 'برنامه تأیید شد — در حال اجرای پژوهش (ممکن است چند دقیقه طول بکشد)…',
    });
    try {
      await api.researchApprove(session.session_id);
      await refresh();
      runEvidence = {
        title: 'اجرای پژوهش',
        steps: [
          { name: 'research.create', detail: session.topic },
          { name: 'research.plan', detail: 'برنامه پیشنهادی' },
          { name: 'research.approve', detail: 'تأیید شما', meta: 'human-in-the-loop' },
          { name: 'research.get', detail: 'گزارش و رویدادها', meta: 'هسته پایتون' },
        ],
      };
    } catch (e) {
      renderStage({ error: msg(e) });
    } finally {
      busy = false;
    }
  }

  async function replan() {
    busy = true;
    renderStage({ busyLabel: 'برنامه‌ریزی مجدد…' });
    try {
      const planned = await api.researchPlan(session.session_id, true);
      session = { ...session, ...planned };
      await refresh();
    } catch (e) {
      renderStage({ error: msg(e) });
    } finally {
      busy = false;
    }
  }

  root.append(
    h(
      'div',
      { class: 'research-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h('div', { class: 'data-ask-row' }, topicInput, startBtn),
        h(
          'div',
          { class: 'data-ask-meta' },
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            'چندمرحله‌ای با تأیید صریح شما',
          ),
          h('span', {
            class: 'faint data-hint',
            text: 'برنامه پیشنهادی را ببینید، تأیید کنید یا دوباره برنامه‌ریزی بخواهید.',
          }),
        ),
      ),
      h(
        'div',
        { class: 'research-pipeline card' },
        h('span', { class: 'micro', text: 'PIPELINE' }),
        h(
          'div',
          { class: 'pipeline-steps' },
          ...PIPELINE.map((s, i) =>
            h(
              'div',
              { class: 'pipeline-step' },
              h('span', { class: 'pipeline-idx mono', text: String(i + 1).padStart(2, '0') }),
              h(
                'div',
                {},
                h('span', { class: 'pipeline-name', text: s.name }),
                h('span', { class: 'pipeline-note', text: s.note }),
              ),
            ),
          ),
        ),
      ),
      stage,
    ),
  );

  renderStage();
}
