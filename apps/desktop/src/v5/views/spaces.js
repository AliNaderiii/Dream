/**
 * Spaces — durable project work surfaces on the REAL space service:
 *  - create spaces (name / language / risk ceiling), attach a folder
 *    IN PLACE through the workspace import (no copying),
 *  - an instruction doc per space, scanned by the real prompt-injection
 *    detector — suspicious docs are quarantined, never silently obeyed,
 *  - automation rules: natural language is parsed into a real cron
 *    expression, shell snippets (!command) are risk-classified, and an
 *    APPROVED draft can be ARMED onto the real scheduler — every later
 *    fire still requires your explicit approval (require_approval).
 * Zero simulations: space.ask / liveloop.role_turn answer with templated
 * local briefings, so they stay unwired (recorded verdict).
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, pickFolder, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const STATUS_FA = {
  APPROVAL_PENDING: { label: 'در انتظار تأیید', cls: 'warn' },
  APPROVED: { label: 'تأییدشده', cls: 'ok' },
  DENIED: { label: 'ردشده', cls: 'err' },
};

const RISK_FA = {
  safe: { label: 'امن', cls: 'ok' },
  guarded: { label: 'محافظه‌کار', cls: 'warn' },
  dangerous: { label: 'خطرناک', cls: 'err' },
};

const LANG_FA = { fa: 'فارسی', en: 'English' };

const chip = (label, cls = '') =>
  h('span', { class: `chip ${cls}`.trim() }, h('span', { class: 'dot' }), label);

const when = (stamp) => (stamp ? new Date(Number(stamp) * 1000).toLocaleString('fa-IR') : '—');

export function spacesView(root, ctx) {
  let mode = 'list'; // 'list' | 'detail'
  let error = null;
  let busy = '';
  let spaces = [];
  let space = null; // space.get() → record + drafts + roles
  const armedInfo = {}; // draft_id → arm result (schedule)

  // singletons reused across re-renders so typing survives
  const nameInput = h('input', {
    class: 'input',
    placeholder: 'نام فضا — مثلاً: فروشگاه آنلاین',
  });
  const langSel = h(
    'select',
    { class: 'input' },
    h('option', { value: 'fa', text: 'زبان: فارسی' }),
    h('option', { value: 'en', text: 'Language: English' }),
  );
  const ceilSel = h(
    'select',
    { class: 'input' },
    h('option', { value: 'guarded', text: 'سقف: محافظه‌کار' }),
    h('option', { value: 'safe', text: 'سقف: امن' }),
  );
  const instrText = h('textarea', {
    class: 'input',
    rows: 5,
    placeholder: 'سند دستوری این فضا — قواعد، ترجیحات و حدود کار. اسکن تزریق پرامپت واقعی است.',
  });
  const ruleText = h('textarea', {
    class: 'input',
    rows: 2,
    placeholder:
      'قاعدهٔ خودکارسازی به زبان ساده — مثلاً: هر روز ساعت ۹ صبح خلاصهٔ یادداشت‌ها را بده',
  });

  const statusHost = h('div', { class: 'sp-status' });
  function renderStatus() {
    const rows = [];
    if (error) rows.push(h('div', { class: 'notice err', html: ic('alert') }, error));
    if (busy) rows.push(h('div', { class: 'notice', html: ic('refresh') }, busy));
    statusHost.replaceChildren(...rows);
  }

  const stage = h('div', { class: 'sp-stage' });

  // ── list ─────────────────────────────────────────────────────────────────
  function spaceCard(row) {
    return h(
      'button',
      {
        class: 'space-card card',
        onclick: () => loadSpace(row.space_id),
      },
      h(
        'div',
        { class: 'space-head' },
        h('span', { class: 'space-name', text: row.name || '—' }),
        chip(LANG_FA[row.language] || row.language || '—'),
        chip(
          row.ceiling === 'safe' ? 'سقف امن' : 'سقف محافظه‌کار',
          row.ceiling === 'safe' ? 'ok' : '',
        ),
      ),
      h(
        'div',
        { class: 'space-meta' },
        h('span', {
          class: 'mono space-folder',
          dir: 'ltr',
          text: row.folder || 'بدون پوشهٔ متصل',
        }),
        h('span', { class: 'muted', text: `به‌روزشده: ${when(row.updated_at)}` }),
      ),
    );
  }

  function renderList() {
    stage.replaceChildren(
      section(
        'NEW SPACE',
        'فضای جدید',
        h(
          'div',
          { class: 'section-card card sp-create' },
          nameInput,
          h('div', { class: 'sp-create-row' }, langSel, ceilSel),
          h(
            'div',
            { class: 'settings-actions' },
            h(
              'button',
              { class: 'btn btn-primary', onclick: doCreate },
              h('span', { html: ic('plus') }),
              'ساخت فضا',
            ),
          ),
        ),
      ),
      section(
        'SPACES',
        'فضاهای من',
        spaces.length === 0
          ? h('div', { class: 'section-card card muted', text: 'هنوز فضایی نساخته‌اید.' })
          : h('div', { class: 'sp-grid' }, ...spaces.map(spaceCard)),
      ),
    );
  }

  async function loadList() {
    busy = 'در حال خواندن فضاها از هسته…';
    error = null;
    renderStatus();
    try {
      const res = await api.spaceList();
      spaces = res?.spaces || [];
      mode = 'list';
      renderList();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function doCreate() {
    const name = nameInput.value.trim();
    if (!name) {
      error = 'نام فضا را بنویسید.';
      renderStatus();
      return;
    }
    busy = 'در حال ساخت فضا…';
    error = null;
    renderStatus();
    try {
      await api.spaceCreate(name, langSel.value, ceilSel.value);
      nameInput.value = '';
      await loadList();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  // ── detail ───────────────────────────────────────────────────────────────
  async function loadSpace(spaceId) {
    busy = 'در حال بارگذاری فضا…';
    error = null;
    renderStatus();
    try {
      const res = await api.spaceGet(spaceId);
      space = res;
      instrText.value = res?.instruction?.text || '';
      mode = 'detail';
      renderDetail();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function reloadSpace() {
    if (!space?.space_id) return;
    try {
      const res = await api.spaceGet(space.space_id);
      space = res;
    } catch (e) {
      error = msg(e);
    }
    renderDetail();
  }

  function instructionCard() {
    const instr = space.instruction;
    const rows = [];
    if (instr) {
      rows.push(
        h(
          'div',
          { class: 'instr-status' },
          chip(`منبع: ${instr.source === 'pasted' ? 'متن چسبانده‌شده' : instr.source}`, ''),
          chip(`${instr.bytes ?? 0} بایت`),
          ...((instr.findings || []).length > 0
            ? instr.findings.map((f) => chip(`یافته: ${f}`, 'warn'))
            : [chip('بدون یافتهٔ مشکوک', 'ok')]),
        ),
      );
    } else {
      rows.push(h('span', { class: 'muted', text: 'این فضا هنوز سند دستوری ندارد.' }));
    }
    return h(
      'div',
      { class: 'section-card card' },
      ...rows,
      instrText,
      h(
        'div',
        { class: 'settings-actions' },
        h(
          'button',
          {
            class: 'btn btn-primary',
            onclick: async () => {
              const text = instrText.value.trim();
              if (!text) {
                error = 'متن سند دستوری خالی است.';
                renderStatus();
                return;
              }
              busy = 'در حال ذخیرهٔ سند (با اسکن تزریق پرامپت)…';
              error = null;
              renderStatus();
              try {
                await api.spaceSetInstruction(space.space_id, { text });
                await reloadSpace();
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
              }
            },
          },
          h('span', { html: ic('check') }),
          'ذخیرهٔ متن',
        ),
        h(
          'button',
          {
            class: 'btn',
            onclick: async () => {
              try {
                const entry = await pickFile('انتخاب سند دستوری');
                if (!entry?.path) return;
                busy = 'در حال بارگذاری سند از فایل…';
                error = null;
                renderStatus();
                await api.spaceSetInstruction(space.space_id, { path: entry.path });
                await reloadSpace();
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
              }
            },
          },
          h('span', { html: ic('upload') }),
          'از فایل…',
        ),
      ),
      h('span', {
        class: 'muted sp-note',
        text: 'اسکن تزریق پرامپت واقعی است — سندی که شبیه تلاش برای بازنویسی دستورها باشد قرنطینه می‌شود.',
      }),
    );
  }

  function rolesCard() {
    const roles = space.roles || [];
    return h(
      'div',
      { class: 'section-card card' },
      ...roles.map((role) =>
        h(
          'div',
          { class: 'role-row' },
          h(
            'div',
            { class: 'role-main' },
            h('span', { class: 'role-name', text: role.name_fa || role.role_id }),
            h('span', { class: 'muted role-job', text: role.job_fa || '' }),
          ),
          chip(`سقف مؤثر: ${role.effective_ceiling === 'safe' ? 'امن' : 'محافظه‌کار'}`),
        ),
      ),
      h('span', {
        class: 'muted sp-note',
        text: 'پرسش زنده از نقش‌ها سیم نشده — پاسخ‌هایش قالبی است (حکم ثبت‌شده). نقش‌ها سقف دسترسی فضا را تعیین می‌کنند.',
      }),
    );
  }

  function draftCard(draft) {
    const st = STATUS_FA[draft.status] || { label: draft.status || '—', cls: '' };
    const arm = armedInfo[draft.draft_id];
    const rows = [];

    if (draft.parse_error) {
      rows.push(
        h(
          'div',
          { class: 'notice warn', html: ic('alert') },
          `زمان‌بندی فهمیده نشد: ${draft.parse_error}`,
        ),
      );
    }
    if (draft.dangerous) {
      rows.push(
        h('div', {
          class: 'notice err',
          html: ic('alert'),
          text: 'شامل فرمان پوستهٔ خطرناک است — هرگز زمان‌بندی نمی‌شود.',
        }),
      );
    }
    for (const sh of draft.shell || []) {
      const r = RISK_FA[sh.risk] || { label: sh.risk || '—', cls: '' };
      rows.push(
        h(
          'div',
          { class: 'shell-row' },
          h('span', { class: 'mono shell-cmd', dir: 'ltr', text: `!${sh.command}` }),
          chip(r.label, r.cls),
        ),
      );
    }
    if (arm?.schedule) {
      const s = arm.schedule;
      rows.push(
        h(
          'div',
          { class: 'schedule-card' },
          h('span', { class: 'micro', text: 'ARMED ON SCHEDULER' }),
          h('span', { class: 'mono', dir: 'ltr', text: s.cron_expression || '—' }),
          chip('هر اجرا نیازمند تأیید', 'ok'),
          s.enabled ? chip('فعال', 'ok') : chip('غیرفعال', ''),
          h(
            'button',
            {
              class: 'btn btn-ghost btn-sm',
              onclick: () =>
                ctx.openEvidence({
                  title: `مسلح‌شدن قاعده روی زمان‌بند`,
                  steps: [
                    { name: 'قاعده', detail: draft.rule || '—' },
                    { name: 'پارس cron', detail: draft.cron || '—', meta: 'nl_to_cron واقعی' },
                    { name: 'تأیید شما', detail: 'space.approve_draft', meta: draft.draft_id },
                    {
                      name: 'liveloop.arm_draft',
                      detail: `schedule_id: ${s.schedule_id || s.id || '—'}`,
                      meta: 'require_approval=true · enabled=' + String(s.enabled),
                    },
                  ],
                }),
            },
            'شواهد',
          ),
        ),
      );
    } else if (draft.armed && draft.schedule_id) {
      rows.push(
        h(
          'div',
          { class: 'schedule-card' },
          h('span', { class: 'micro', text: 'ARMED ON SCHEDULER' }),
          h('span', { class: 'mono', dir: 'ltr', text: draft.schedule_id }),
          chip('هر اجرا نیازمند تأیید', 'ok'),
        ),
      );
    }

    const actions = [];
    if (draft.status === 'APPROVAL_PENDING') {
      actions.push(
        h('button', { class: 'btn btn-sm btn-primary', onclick: () => doApprove(draft) }, 'تأیید'),
        h('button', { class: 'btn btn-sm', onclick: () => doDeny(draft) }, 'رد'),
      );
    } else if (draft.status === 'APPROVED' && !draft.armed && !armedInfo[draft.draft_id]) {
      actions.push(
        h(
          'button',
          { class: 'btn btn-sm btn-primary', onclick: () => doArm(draft) },
          'مسلح‌کردن روی زمان‌بند',
        ),
        h('button', { class: 'btn btn-sm', onclick: () => doDeny(draft) }, 'رد'),
      );
    }

    return h(
      'div',
      { class: 'draft-card', dataset: { draft: draft.draft_id } },
      h(
        'div',
        { class: 'draft-head' },
        h('span', { class: 'draft-rule', text: draft.rule || '—' }),
        chip(st.label, st.cls),
      ),
      draft.cron
        ? h('span', { class: 'mono draft-cron', dir: 'ltr', text: `cron: ${draft.cron}` })
        : null,
      h('span', { class: 'muted draft-when', text: `ثبت: ${when(draft.created_at)}` }),
      ...rows,
      actions.length > 0 ? h('div', { class: 'draft-actions' }, ...actions) : null,
    );
  }

  function renderDetail() {
    const drafts = space.drafts || [];
    stage.replaceChildren(
      h(
        'button',
        {
          class: 'btn btn-ghost btn-sm sp-back',
          onclick: () => loadList(),
        },
        h('span', { html: ic('refresh') }),
        '← همهٔ فضاها',
      ),
      section(
        'SPACE',
        space.name || '—',
        h(
          'div',
          { class: 'section-card card' },
          h(
            'div',
            { class: 'space-head' },
            chip(LANG_FA[space.language] || space.language || '—'),
            chip(
              space.ceiling === 'safe' ? 'سقف امن' : 'سقف محافظه‌کار',
              space.ceiling === 'safe' ? 'ok' : '',
            ),
            h(
              'button',
              {
                class: 'btn btn-sm sp-archive',
                onclick: async () => {
                  if (!window.confirm(`فضای «${space.name}» بایگانی شود؟`)) return;
                  try {
                    await api.spaceArchive(space.space_id);
                    await loadList();
                  } catch (e) {
                    error = msg(e);
                    renderStatus();
                  }
                },
              },
              'بایگانی',
            ),
          ),
          h(
            'div',
            { class: 'sp-folder-row' },
            h('span', {
              class: 'mono space-folder',
              dir: 'ltr',
              text: space.folder || 'بدون پوشهٔ متصل',
            }),
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  try {
                    const folder = await pickFolder('انتخاب پوشهٔ این فضا');
                    if (!folder) return;
                    busy = 'در حال اتصال پوشه (در جای خود، بدون کپی)…';
                    error = null;
                    renderStatus();
                    await api.spaceAttachFolder(space.space_id, folder);
                    await reloadSpace();
                  } catch (e) {
                    error = msg(e);
                  } finally {
                    busy = '';
                    renderStatus();
                  }
                },
              },
              h('span', { html: ic('folder') }),
              'اتصال پوشه…',
            ),
          ),
          space.root_id
            ? chip(`ریشهٔ ثبت‌شده: ${String(space.root_id).slice(0, 14)}…`, 'ok')
            : null,
        ),
      ),
      section('INSTRUCTION', 'سند دستوری', instructionCard()),
      section('ROLES', 'نقش‌های تخصصی این فضا', rolesCard()),
      section(
        'AUTOMATION',
        'قواعد خودکارسازی',
        h(
          'div',
          { class: 'section-card card' },
          ruleText,
          h(
            'div',
            { class: 'settings-actions' },
            h(
              'button',
              {
                class: 'btn btn-primary',
                onclick: async () => {
                  const rule = ruleText.value.trim();
                  if (!rule) {
                    error = 'قاعده را بنویسید.';
                    renderStatus();
                    return;
                  }
                  busy = 'در حال ثبت قاعده و پارس زمان‌بندی…';
                  error = null;
                  renderStatus();
                  try {
                    await api.spaceProposeDraft(space.space_id, rule);
                    ruleText.value = '';
                    await reloadSpace();
                  } catch (e) {
                    error = msg(e);
                  } finally {
                    busy = '';
                    renderStatus();
                  }
                },
              },
              h('span', { html: ic('plus') }),
              'ثبت قاعده',
            ),
          ),
          h('span', {
            class: 'muted sp-note',
            text: 'زبان ساده به cron واقعی پارس می‌شود؛ فرمان‌های !پوسته طبقه‌بندی ریسک می‌شوند. قاعدهٔ تأییدشده روی زمان‌بند واقعی مسلح می‌شود و هر اجرا همچنان نیازمند تأیید شماست.',
          }),
          drafts.length === 0
            ? h('span', { class: 'muted', text: 'هنوز قاعده‌ای ثبت نشده است.' })
            : h('div', { class: 'drafts-list' }, ...drafts.map(draftCard)),
        ),
      ),
    );
  }

  async function doApprove(draft) {
    busy = 'در حال تأیید قاعده…';
    error = null;
    renderStatus();
    try {
      await api.spaceApproveDraft(draft.draft_id);
      await reloadSpace();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function doDeny(draft) {
    busy = 'در حال رد قاعده…';
    error = null;
    renderStatus();
    try {
      await api.spaceDenyDraft(draft.draft_id);
      delete armedInfo[draft.draft_id];
      await reloadSpace();
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStatus();
    }
  }

  async function doArm(draft) {
    busy = 'در حال مسلح‌کردن روی زمان‌بند واقعی…';
    error = null;
    renderStatus();
    try {
      const res = await api.llArmDraft(draft.draft_id);
      armedInfo[draft.draft_id] = res;
      await reloadSpace();
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
      { class: 'spaces-view' },
      statusHost,
      h(
        'div',
        { class: 'rt-toolbar' },
        h(
          'span',
          { class: 'muted rt-honesty' },
          'فضاها پایدارند (data/spaces.json)؛ پوشه در جای خود متصل می‌شود و قواعد تأییدشده روی زمان‌بند واقعی مسلح می‌شوند — هر اجرا نیازمند تأیید شما.',
        ),
        h(
          'button',
          { class: 'btn btn-sm', onclick: () => (mode === 'detail' ? reloadSpace() : loadList()) },
          h('span', { html: ic('refresh') }),
          'به‌روزرسانی',
        ),
      ),
      stage,
    ),
  );

  renderList();
  loadList();
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
