/**
 * Agent mode — four REAL workbenches on the agent-modes service:
 *  - «هدف»:  an objective plus YOUR acceptance criteria; the core verifies
 *    each criterion with an honest RULE-BASED evaluator (real filenames
 *    under registered workspace roots, listing-cap compliance, impossible
 *    markers refused) and says "unable" out loud when it cannot verify.
 *  - «پوسته»: guarded !shell — propose, see the risk tier, approve, then a
 *    REAL subprocess runs: network off (PATH=/usr/bin:/bin), guarded
 *    commands confined to a registered workspace root, dangerous commands
 *    never spawn even if approved.
 *  - «وضعیت»: the live status registry — recent goals and subagent
 *    bookkeeping, with a real stop that cancels through engine tokens.
 *  - «مراجع و فرمان‌ها»: explicit @file/#conversation//command/!shell
 *    parsing, safe file preview, conversation references, and the real
 *    Persian/English command palette — nothing opens or executes itself.
 * Zero simulations: agentmode_plan/agentmode_continue draft three fixed
 * template steps and mark them done without doing any work — they stay
 * unwired (recorded verdict).
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const GOAL_STATUS_FA = {
  running: { label: 'در حال اجرا', cls: '' },
  complete: { label: 'برآورده شد', cls: 'ok' },
  unable: { label: 'ناتوان — صادقانه', cls: 'warn' },
  cancelled: { label: 'لغوشده', cls: 'err' },
};

const RISK_FA = {
  safe: { label: 'امن', cls: 'ok' },
  guarded: { label: 'محافظه‌کار', cls: 'warn' },
  dangerous: { label: 'خطرناک', cls: 'err' },
};

const chip = (label, cls = '') =>
  h('span', { class: `chip ${cls}`.trim() }, h('span', { class: 'dot' }), label);

const when = (stamp) => (stamp ? new Date(Number(stamp) * 1000).toLocaleString('fa-IR') : '—');

export function agentView(root, ctx) {
  let mode = 'goal'; // 'goal' | 'shell' | 'status' | 'refs'
  let error = null;
  let busy = '';

  // ── shared chrome ────────────────────────────────────────────────────────
  const statusHost = h('div', { class: 'ag-status' });
  function renderStatus() {
    const rows = [];
    if (error) rows.push(h('div', { class: 'notice err', html: ic('alert') }, error));
    if (busy) rows.push(h('div', { class: 'notice', html: ic('refresh') }, busy));
    statusHost.replaceChildren(...rows);
  }

  const tabs = h(
    'div',
    { class: 'voice-tabs' },
    tabBtn('goal', 'هدف'),
    tabBtn('shell', 'پوسته'),
    tabBtn('status', 'وضعیت زنده'),
    tabBtn('refs', 'مراجع و فرمان‌ها'),
  );

  function tabBtn(id, label) {
    return h(
      'button',
      {
        class: `voice-tab${mode === id ? ' active' : ''}`,
        dataset: { tab: id },
        onclick: () => {
          mode = id;
          for (const b of tabs.querySelectorAll('.voice-tab')) {
            b.classList.toggle('active', b.dataset.tab === id);
          }
          paneHost.replaceChildren(...panes[id].render());
          if (id === 'status') panes.status.refresh();
          if (id === 'refs') panes.refs.refresh();
        },
      },
      label,
    );
  }

  const paneHost = h('div', { class: 'thinking-pane' });

  // ════════════════ tab 1: goal ═══════════════════════════════════════════
  let goal = null; // latest goal record

  const objectiveInput = h('input', {
    class: 'input',
    placeholder: 'هدف — مثلاً: گزارش ماهانه از فایل‌های فروش آماده شود',
  });
  const criteriaInput = h('textarea', {
    class: 'input',
    rows: 4,
    placeholder:
      'معیارهای پذیرش — هر خط یک معیار:\nفایل sales.xlsx در فضای کاری موجود باشد\nلیست‌گذاری‌ها سقف داشته باشند',
  });

  function criterionRow(row) {
    return h(
      'div',
      { class: 'crit-row' },
      chip(row.met ? 'برآورده' : 'برآورده نشد', row.met ? 'ok' : 'err'),
      h('span', { class: 'crit-text', text: row.criterion }),
      h('span', { class: 'muted crit-reason', text: row.reason || '' }),
    );
  }

  function renderGoal() {
    const children = [
      h(
        'div',
        { class: 'section-card card' },
        objectiveInput,
        criteriaInput,
        h(
          'div',
          { class: 'settings-actions' },
          h(
            'button',
            {
              class: 'btn btn-primary',
              onclick: async () => {
                const objective = objectiveInput.value.trim();
                const criteria = criteriaInput.value
                  .split('\n')
                  .map((l) => l.trim())
                  .filter(Boolean);
                if (!objective || criteria.length === 0) {
                  error = 'هدف و حداقل یک معیار لازم است.';
                  renderStatus();
                  return;
                }
                busy = 'در حال ارزیابی معیارها روی فضای کاری واقعی…';
                error = null;
                renderStatus();
                try {
                  goal = await api.amGoal(objective, criteria);
                  renderGoalPane();
                } catch (e) {
                  error = msg(e);
                } finally {
                  busy = '';
                  renderStatus();
                }
              },
            },
            h('span', { html: ic('target') }),
            'شروع و ارزیابی',
          ),
        ),
        h('span', {
          class: 'muted ag-note',
          text: 'ارزیاب قاعده‌محور است: نام فایل‌های واقعی ریشه‌های ثبت‌شدهٔ فضای کاری، رعایت سقف لیست‌گذاری و نشانگرهای ناممکن (شبکه و…) بررسی می‌شود — نه LLM. معیاری که بومی قابل تأیید نباشد، صادقانه «ناتوان» اعلام می‌شود.',
        }),
      ),
    ];

    if (goal) {
      const st = GOAL_STATUS_FA[goal.status] || { label: goal.status || '—', cls: '' };
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h(
            'div',
            { class: 'goal-head' },
            chip(st.label, st.cls),
            h('span', { class: 'goal-objective', text: goal.objective || '—' }),
          ),
          h('div', { class: 'crits' }, ...(goal.results || []).map(criterionRow)),
          h('span', { class: 'muted goal-report', text: goal.report || '' }),
          h(
            'div',
            { class: 'settings-actions' },
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  busy = 'در حال ارزیابی دوباره…';
                  error = null;
                  renderStatus();
                  try {
                    goal = await api.amReport(goal.goal_id);
                    renderGoalPane();
                  } catch (e) {
                    error = msg(e);
                  } finally {
                    busy = '';
                    renderStatus();
                  }
                },
              },
              h('span', { html: ic('refresh') }),
              'ارزیابی دوباره',
            ),
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  busy = 'در حال توقف هدف…';
                  error = null;
                  renderStatus();
                  try {
                    await api.amStop({ goalId: goal.goal_id });
                    goal = await api.amReport(goal.goal_id);
                    renderGoalPane();
                  } catch (e) {
                    error = msg(e);
                  } finally {
                    busy = '';
                    renderStatus();
                  }
                },
              },
              h('span', { html: ic('x') }),
              'توقف',
            ),
            h(
              'button',
              {
                class: 'btn btn-ghost btn-sm',
                onclick: () =>
                  ctx.openEvidence({
                    title: 'ارزیابی هدف',
                    steps: [
                      {
                        name: 'workspace.agentmode_goal',
                        detail: goal.objective || '—',
                        meta: 'ارزیاب قاعده‌محور — نه LLM',
                      },
                      ...(goal.results || []).map((r) => ({
                        name: r.met ? 'برآورده' : 'برآورده نشد',
                        detail: r.criterion,
                        meta: r.reason || '',
                      })),
                      { name: 'گزارش', detail: goal.report || '—', meta: goal.goal_id },
                    ],
                  }),
              },
              'شواهد',
            ),
          ),
        ),
      );
    }
    return children;
  }

  // ════════════════ tab 2: shell ══════════════════════════════════════════
  let proposal = null; // shell_propose result
  let execution = null; // shell_execute result
  let roots = [];

  const cmdInput = h('input', {
    class: 'input mono',
    dir: 'ltr',
    placeholder: 'ls -la',
  });
  const cwdSel = h('select', { class: 'input' });

  function renderCwdOptions() {
    cwdSel.replaceChildren(
      h('option', { value: '', text: 'بدون ریشه — پوشهٔ موقت (فقط فرمان‌های امن)' }),
      ...roots.map((r) =>
        h('option', { value: r.path || '', text: r.name || r.path || r.root_id }),
      ),
    );
  }

  function renderShell() {
    const children = [
      h(
        'div',
        { class: 'section-card card' },
        cmdInput,
        h(
          'label',
          { class: 'field' },
          h('span', {
            class: 'field-label',
            text: 'ریشهٔ اجرا (فرمان‌های محافظه‌کار به ریشهٔ ثبت‌شده نیاز دارند)',
          }),
          cwdSel,
        ),
        h(
          'div',
          { class: 'settings-actions' },
          h(
            'button',
            {
              class: 'btn btn-primary',
              onclick: async () => {
                const command = cmdInput.value.trim();
                if (!command) {
                  error = 'فرمان را بنویسید.';
                  renderStatus();
                  return;
                }
                busy = 'در حال طبقه‌بندی ریسک فرمان…';
                error = null;
                execution = null;
                renderStatus();
                try {
                  proposal = await api.shPropose(command, cwdSel.value || undefined);
                  renderShellPane();
                } catch (e) {
                  error = msg(e);
                } finally {
                  busy = '';
                  renderStatus();
                }
              },
            },
            h('span', { html: ic('terminal') }),
            'پیشنهاد فرمان',
          ),
        ),
        h('span', {
          class: 'muted ag-note',
          text: 'اجرا واقعی است: شبکه خاموش (PATH=/usr/bin:/bin)، فرمان‌های محافظه‌کار فقط داخل ریشهٔ ثبت‌شدهٔ فضای کاری، مسیرهای والد رد می‌شوند و فرمان خطرناک هرگز spawn نمی‌شود — حتی با تأیید شما.',
        }),
      ),
    ];

    if (proposal) {
      const risk = RISK_FA[proposal.risk] || { label: proposal.risk || '—', cls: '' };
      const rows = [
        h(
          'div',
          { class: 'shell-prop' },
          h('span', { class: 'mono shell-cmd', dir: 'ltr', text: proposal.command }),
          chip(risk.label, risk.cls),
          proposal.network ? chip('شبکه روشن', 'warn') : chip('شبکه خاموش', 'ok'),
        ),
      ];
      if (proposal.risk === 'dangerous') {
        rows.push(
          h('div', {
            class: 'notice err',
            html: ic('alert'),
            text: 'فرمان خطرناک است — دریم هرگز آن را اجرا نمی‌کند، حتی با تأیید شما.',
          }),
        );
      } else {
        rows.push(
          h(
            'div',
            { class: 'settings-actions' },
            h(
              'button',
              {
                class: 'btn btn-primary',
                onclick: async () => {
                  busy = 'در حال اجرای واقعی فرمان…';
                  error = null;
                  renderStatus();
                  try {
                    execution = await api.shExecute(proposal.approval_id);
                    renderShellPane();
                  } catch (e) {
                    error = msg(e);
                  } finally {
                    busy = '';
                    renderStatus();
                  }
                },
              },
              h('span', { html: ic('check') }),
              proposal.requires_approval ? 'تأیید و اجرا' : 'اجرا',
            ),
          ),
        );
      }
      children.push(h('div', { class: 'section-card card' }, ...rows));
    }

    if (execution) {
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h(
            'div',
            { class: 'shell-res-head' },
            chip(
              `کد خروج: ${execution.returncode ?? '—'}`,
              execution.returncode === 0 ? 'ok' : 'warn',
            ),
            execution.timed_out ? chip('اتمام زمان', 'err') : null,
            execution.executed ? chip('اجرا شد', '') : chip('اجرا نشد', 'err'),
          ),
          execution.stdout
            ? h('pre', { class: 'shell-out mono', dir: 'ltr', text: execution.stdout })
            : null,
          execution.stderr
            ? h('pre', { class: 'shell-err mono', dir: 'ltr', text: execution.stderr })
            : null,
        ),
      );
    }
    return children;
  }

  // ════════════════ tab 3: live status ═════════════════════════════════════
  let live = null; // agentmode_status result

  function renderStatusTab() {
    if (!live) {
      return [h('span', { class: 'muted', text: 'وضعیت زنده از هسته خوانده می‌شود…' })];
    }
    const goals = live.goals || [];
    const subs = live.subagents || [];
    return [
      h(
        'div',
        { class: 'section-card card' },
        h(
          'div',
          { class: 'goal-head' },
          chip(live.running ? 'فعال' : 'غیرفعال', live.running ? 'ok' : ''),
          live.cancelled ? chip('لغو اخیر', 'warn') : null,
          live.live ? chip('زنده', 'ok') : null,
          h(
            'button',
            {
              class: 'btn btn-sm sp-archive',
              onclick: async () => {
                busy = 'در حال توقف همه…';
                error = null;
                renderStatus();
                try {
                  await api.amStop({});
                  await panes.status.refresh();
                } catch (e) {
                  error = msg(e);
                } finally {
                  busy = '';
                  renderStatus();
                }
              },
            },
            'توقف همه',
          ),
        ),
        h('span', { class: 'micro', text: 'GOALS' }),
        goals.length === 0
          ? h('span', { class: 'muted', text: 'هدفی ثبت نشده است.' })
          : h(
              'div',
              { class: 'crits' },
              ...goals.map((g) => {
                const st = GOAL_STATUS_FA[g.status] || { label: g.status || '—', cls: '' };
                return h(
                  'div',
                  { class: 'crit-row' },
                  chip(st.label, st.cls),
                  h('span', { class: 'crit-text', text: g.objective || '—' }),
                  h('span', { class: 'muted crit-reason', text: when(g.updated_at) }),
                );
              }),
            ),
        h('span', { class: 'micro', text: 'SUBAGENTS' }),
        subs.length === 0
          ? h('span', { class: 'muted', text: 'زیرایجنتی فعال نیست.' })
          : h(
              'div',
              { class: 'crits' },
              ...subs.map((s) =>
                h(
                  'div',
                  { class: 'crit-row' },
                  chip(
                    s.status || '—',
                    s.status === 'running' ? 'ok' : s.status === 'cancelled' ? 'err' : '',
                  ),
                  h('span', {
                    class: 'crit-text',
                    text: `${s.name || '—'} · ${Math.round((s.progress || 0) * 100)}٪`,
                  }),
                  h('span', { class: 'muted crit-reason', text: s.latest_action || '' }),
                ),
              ),
            ),
      ),
    ];
  }

  // ════════════════ tab 4: references + commands ═════════════════════════
  let parsedRefs = null;
  let filePreview = null;
  let conversationRef = null;
  let commandPalette = null;
  const refsInput = h('textarea', {
    class: 'input',
    rows: 3,
    placeholder: '@sales.csv #session-id /goal !ls -la',
  });
  const refsPath = h('input', {
    class: 'input mono',
    dir: 'ltr',
    placeholder: 'نسبت به ریشه: sales.csv',
  });
  const refsSession = h('input', {
    class: 'input mono',
    dir: 'ltr',
    placeholder: 'شناسهٔ نشست گفتگو',
  });
  const commandQuery = h('input', { class: 'input mono', dir: 'ltr', placeholder: '/go یا goal' });
  const refsRoot = h('select', { class: 'input' });

  function renderRefsRoots() {
    refsRoot.replaceChildren(
      h('option', { value: '', text: 'ریشهٔ ثبت‌شده را انتخاب کنید' }),
      ...roots.map((r) =>
        h('option', { value: r.root_id || '', text: r.name || r.path || r.root_id }),
      ),
    );
  }

  function renderRefs() {
    const children = [
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'REFERENCE PARSER' }),
        h('span', {
          class: 'muted ag-note',
          text: 'مراجع فقط وقتی دنبال می‌شوند که خودتان صریحاً بنویسید: @فایل، #نشست، /فرمان یا !پوسته.',
        }),
        refsInput,
        h(
          'button',
          {
            class: 'btn btn-primary',
            onclick: async () => {
              if (!refsInput.value.trim()) return;
              busy = 'در حال تجزیهٔ مراجع واقعی…';
              error = null;
              renderStatus();
              try {
                parsedRefs = await api.refsParse(refsInput.value.trim());
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
                renderRefsPane();
              }
            },
          },
          h('span', { html: ic('search') }),
          'تجزیهٔ مراجع',
        ),
        h('span', {
          class: 'muted ag-note',
          text: 'تجزیه فقط گزارش می‌دهد؛ هیچ فایل، نشست یا فرمانی خودکار باز یا اجرا نمی‌شود.',
        }),
      ),
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'FILE REFERENCE' }),
        refsRoot,
        refsPath,
        h(
          'button',
          {
            class: 'btn',
            onclick: async () => {
              if (!refsRoot.value || !refsPath.value.trim()) return;
              busy = 'در حال خواندن پیش‌نمایش فایل از هسته…';
              error = null;
              renderStatus();
              try {
                filePreview = await api.refsFile(refsRoot.value, refsPath.value.trim());
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
                renderRefsPane();
              }
            },
          },
          'پیش‌نمایش فایل',
        ),
      ),
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'CONVERSATION REFERENCE' }),
        refsSession,
        h(
          'button',
          {
            class: 'btn',
            onclick: async () => {
              if (!refsSession.value.trim()) return;
              busy = 'در حال resolve کردن شناسهٔ نشست…';
              error = null;
              renderStatus();
              try {
                conversationRef = await api.refsConversation(refsSession.value.trim());
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
                renderRefsPane();
              }
            },
          },
          'resolve نشست',
        ),
      ),
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'COMMAND PALETTE' }),
        commandQuery,
        h(
          'button',
          {
            class: 'btn',
            onclick: async () => {
              busy = 'در حال خواندن فهرست فرمان‌های هسته…';
              error = null;
              renderStatus();
              try {
                commandPalette = await api.commandsList(commandQuery.value.trim());
              } catch (e) {
                error = msg(e);
              } finally {
                busy = '';
                renderStatus();
                renderRefsPane();
              }
            },
          },
          'فهرست فرمان‌ها',
        ),
      ),
    ];
    if (parsedRefs)
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h('span', { class: 'micro', text: 'PARSED' }),
          h('pre', {
            class: 'shell-out mono',
            dir: 'ltr',
            text: JSON.stringify(parsedRefs, null, 2),
          }),
        ),
      );
    if (filePreview)
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h('span', { class: 'micro', text: 'FILE PREVIEW' }),
          h('div', { class: 'result-text', text: filePreview.summary || filePreview.path || '—' }),
          h('span', {
            class: 'muted',
            text: `${filePreview.type || 'file'} · مسیر از هستهٔ فضای کاری`,
          }),
        ),
      );
    if (conversationRef)
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h('span', { class: 'micro', text: 'CONVERSATION' }),
          h('div', { class: 'result-text', text: conversationRef.reference || '—' }),
        ),
      );
    if (commandPalette)
      children.push(
        h(
          'div',
          { class: 'section-card card' },
          h('span', { class: 'micro', text: 'COMMANDS' }),
          ...(commandPalette.commands || []).map((c) =>
            h(
              'div',
              { class: 'crit-row' },
              h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), c.title),
              h('span', { class: 'crit-text', text: c.summary }),
            ),
          ),
        ),
      );
    return children;
  }

  const panes = {
    goal: { render: renderGoal },
    shell: {
      render: renderShell,
      refresh: async () => {
        try {
          roots = (await api.wsRootsList())?.roots || [];
        } catch {
          roots = [];
        }
        renderCwdOptions();
      },
    },
    status: {
      render: renderStatusTab,
      refresh: async () => {
        try {
          live = await api.amStatus();
        } catch {
          live = null;
        }
        paneHost.replaceChildren(...renderStatusTab());
      },
    },
    refs: {
      render: renderRefs,
      refresh: async () => {
        try {
          roots = (await api.wsRootsList())?.roots || [];
        } catch {
          roots = [];
        }
        renderRefsRoots();
      },
    },
  };

  function renderGoalPane() {
    if (mode === 'goal') paneHost.replaceChildren(...renderGoal());
  }
  function renderShellPane() {
    if (mode === 'shell') paneHost.replaceChildren(...renderShell());
  }
  function renderRefsPane() {
    if (mode === 'refs') paneHost.replaceChildren(...renderRefs());
  }

  // ── layout ───────────────────────────────────────────────────────────────
  root.append(h('div', { class: 'agent-view' }, statusHost, tabs, paneHost));

  paneHost.replaceChildren(...renderGoal());
  panes.shell.refresh();
}
