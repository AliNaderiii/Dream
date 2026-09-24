/**
 * Thinking — two real workbenches on the reasoning/dialectic engines:
 *  - «درخت استدلال»: a Tree-of-Thoughts where YOU write the candidate
 *    thoughts; the core keeps the tree, scores with an honest RULE-BASED
 *    evaluator (length/coherence/depth — not an LLM), prunes, and
 *    synthesizes the winning path.
 *  - «مدل ذهنی»: a real belief graph — add beliefs, link them, detect
 *    tensions with a rule-based opposite-pairs matcher, and reconcile
 *    contradictions with your own nuanced statement.
 * The swarm engine and the templated 3-agent debate stay unwired by design
 * (their outputs are simulations, and this app ships zero simulations).
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const NODE_STATUS_FA = {
  active: { label: 'فعال', cls: '' },
  pruned: { label: 'هرس‌شده', cls: 'err' },
};

const BELIEF_STATUS_FA = {
  active: { label: 'فعال', cls: 'ok' },
  contradicted: { label: 'در تناقض', cls: 'warn' },
  nuanced: { label: 'بدیل‌سازی‌شده', cls: '' },
};

export function thinkingView(root, ctx) {
  let mode = 'tree'; // 'tree' | 'model'
  let error = null;

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  // ════════════════ tab 1: reasoning tree ═════════════════════════════════
  let traj = null; // {trajectory_id, goal, root_node_id, trajectory}
  let selectedNode = null;
  let synthesis = null;
  let busy = '';

  const goalInput = h('input', {
    class: 'input',
    placeholder: 'هدف استدلال — مثلاً: انتخاب معماری داده برای تیم کوچک',
  });
  const thoughtsInput = h('textarea', {
    class: 'input',
    rows: 3,
    placeholder:
      'فکرهای کاندید — هر خط یک فکر:\nگزینه اول را امتحان می‌کنیم چون...\nگزینه دوم ریسک کمتری دارد چون...',
  });
  const treeStage = h('div', { class: 'thinking-stage' });

  function nodeRow(node, depth) {
    const st = NODE_STATUS_FA[node.status] || { label: node.status || '—', cls: '' };
    return h(
      'button',
      {
        class: `files-row tree-node${selectedNode === node.node_id ? ' selected' : ''}`,
        style: `padding-inline-start:${10 + depth * 18}px;`,
        onclick: () => {
          selectedNode = node.node_id;
          renderTree();
        },
      },
      h('span', { class: 'files-row-ic', html: ic(node.children_ids?.length ? 'folder' : 'file') }),
      h(
        'div',
        { class: 'files-row-main' },
        h('span', { class: 'files-row-name', text: node.thought_content || '—' }),
        h('span', {
          class: 'files-row-meta mono',
          text: `${node.node_id.slice(0, 8)} · عمق ${node.depth ?? 0}`,
        }),
      ),
      node.score != null
        ? h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `امتیاز ${Number(node.score).toFixed(2)}`,
          )
        : null,
      h('span', { class: `chip ${st.cls}` }, h('span', { class: 'dot' }), st.label),
    );
  }

  /** The core serialises tree nodes as a LIST — index it by node_id. */
  function nodesById(trajectory) {
    const list = Array.isArray(trajectory?.nodes) ? trajectory.nodes : [];
    return Object.fromEntries(list.map((n) => [n.node_id, n]));
  }

  function flattenTree(trajectory, rootId) {
    const dict = nodesById(trajectory);
    const rows = [];
    const walk = (id, depth) => {
      const n = dict[id];
      if (!n) return;
      rows.push([n, depth]);
      for (const c of n.children_ids || []) walk(c, depth + 1);
    };
    walk(rootId, 0);
    return rows;
  }

  function renderTree() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, busy));

    if (!traj) {
      children.push(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('brain') }),
          h('span', { class: 'empty-title', text: 'یک هدف بدهید تا درخت استدلال ساخته شود' }),
          h('span', {
            class: 'empty-note',
            text: 'شما فکرهای کاندید را می‌نویسید؛ هسته درخت را نگه می‌دارد، با ارزیاب قاعده‌محور امتیاز می‌دهد، شاخه‌های ضعیف را هرس می‌کند و مسیر برنده را سنتز می‌کند.',
          }),
        ),
      );
    } else {
      children.push(
        h(
          'div',
          { class: 'result-meta' },
          h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), `هدف: ${traj.goal}`),
          h(
            'span',
            { class: 'chip mono' },
            h('span', { class: 'dot' }),
            traj.trajectory_id.slice(0, 12),
          ),
        ),
        h(
          'div',
          { class: 'files-list card' },
          ...flattenTree(traj.trajectory, traj.root_node_id).map(([n, d]) => nodeRow(n, d)),
        ),
        h(
          'div',
          { class: 'result-panel card' },
          h('span', {
            class: 'micro',
            text: selectedNode ? 'SELECTED NODE' : 'CANDIDATE THOUGHTS',
          }),
          selectedNode
            ? h('span', {
                class: 'empty-note',
                text: 'فکرهای کاندید زیر به گره انتخاب‌شده اضافه می‌شوند (یا با جستجوی MCTS گسترش می‌یابند).',
              })
            : null,
          thoughtsInput,
          h(
            'div',
            { class: 'voice-actions' },
            h(
              'button',
              {
                class: 'btn btn-primary',
                disabled: !!busy || !thoughtsInput.value.trim(),
                onclick: expand,
              },
              h('span', { html: ic('plus') }),
              'گسترش با فکرهای من',
            ),
            h(
              'button',
              { class: 'btn', disabled: !!busy || !thoughtsInput.value.trim(), onclick: mcts },
              h('span', { html: ic('refresh') }),
              'یک گام MCTS با همین فکرها',
            ),
            selectedNode
              ? h(
                  'button',
                  { class: 'btn', disabled: !!busy, onclick: critique },
                  h('span', { html: ic('search') }),
                  'نقد قاعده‌محور گره',
                )
              : null,
            h(
              'button',
              { class: 'btn', disabled: !!busy, onclick: prune },
              h('span', { html: ic('x') }),
              'هرس شاخه‌های ضعیف',
            ),
            h(
              'button',
              { class: 'btn', disabled: !!busy, onclick: synthesize },
              h('span', { html: ic('check') }),
              'سنتز پاسخ نهایی',
            ),
          ),
        ),
      );
      if (synthesis) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'SYNTHESIS' }),
            h('pre', { class: 'files-preview-text' }, synthesis.final_answer || '—'),
            h(
              'div',
              { class: 'result-meta' },
              h(
                'span',
                { class: 'chip ok' },
                h('span', { class: 'dot' }),
                `اطمینان: ${synthesis.confidence ?? '—'}`,
              ),
              h(
                'span',
                { class: 'chip' },
                h('span', { class: 'dot' }),
                `${synthesis.selected_path?.length ?? 0} گره در مسیر برنده`,
              ),
              h(
                'button',
                {
                  class: 'btn btn-sm evidence-link',
                  onclick: () =>
                    ctx.openEvidence({
                      title: 'سنتز استدلال',
                      steps: [
                        { name: 'reasoning.plan_tree', detail: traj.goal, meta: 'هسته پایتون' },
                        {
                          name: 'فکرهای کاندید',
                          detail: 'نوشتهٔ کاربر',
                          meta: 'human-in-the-loop',
                        },
                        {
                          name: 'ارزیاب',
                          detail: 'قاعده‌محور (طول/انسجام/عمق) — نه LLM',
                          meta: 'هuristic',
                        },
                        {
                          name: 'reasoning.synthesize_solution',
                          detail: `اطمینان ${synthesis.confidence ?? '—'}`,
                          meta: 'مسیر برنده',
                        },
                      ],
                    }),
                },
                h('span', { html: ic('evidence') }),
                'شواهد',
              ),
            ),
          ),
        );
      }
    }
    treeStage.replaceChildren(...children);
  }

  async function refreshTree() {
    try {
      const res = await api.reasoningStats(traj.trajectory_id);
      if (res?.trajectory) {
        traj = { ...traj, trajectory: res.trajectory };
      }
    } catch {
      /* stats optional — tree snapshot may already be fresh from responses */
    }
    renderTree();
  }

  async function plan() {
    const goal = goalInput.value.trim();
    if (!goal) return;
    busy = 'در حال ساخت درخت…';
    error = null;
    renderTree();
    try {
      const res = await api.reasoningPlanTree(goal);
      traj = {
        trajectory_id: res.trajectory_id,
        root_node_id: res.root_node_id,
        goal,
        trajectory: res.trajectory,
      };
      selectedNode = null;
      synthesis = null;
      goalInput.value = '';
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderTree();
    }
  }

  function thoughtList() {
    return thoughtsInput.value
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
  }

  async function expand() {
    const thoughts = thoughtList();
    if (!thoughts.length || !traj) return;
    busy = 'در حال گسترش…';
    error = null;
    renderTree();
    try {
      const parentId = selectedNode || traj.root_node_id;
      await api.reasoningExpand(traj.trajectory_id, parentId, thoughts);
      thoughtsInput.value = '';
      await refreshTree();
    } catch (e) {
      error = msg(e);
      renderTree();
    } finally {
      busy = '';
      renderTree();
    }
  }

  async function mcts() {
    const thoughts = thoughtList();
    if (!thoughts.length || !traj) return;
    busy = 'یک گام MCTS (انتخاب → گسترش → ارزیابی → بازانتشار)…';
    error = null;
    renderTree();
    try {
      await api.reasoningMcts(traj.trajectory_id, thoughts);
      thoughtsInput.value = '';
      await refreshTree();
    } catch (e) {
      error = msg(e);
      renderTree();
    } finally {
      busy = '';
      renderTree();
    }
  }

  async function critique() {
    if (!selectedNode || !traj) return;
    busy = 'در حال نقد قاعده‌محور…';
    error = null;
    renderTree();
    try {
      await api.reasoningCritique(traj.trajectory_id, selectedNode);
      await refreshTree();
    } catch (e) {
      error = msg(e);
      renderTree();
    } finally {
      busy = '';
      renderTree();
    }
  }

  async function prune() {
    if (!traj) return;
    busy = 'در حال هرس…';
    error = null;
    renderTree();
    try {
      await api.reasoningBacktrack(traj.trajectory_id);
      await refreshTree();
    } catch (e) {
      error = msg(e);
      renderTree();
    } finally {
      busy = '';
      renderTree();
    }
  }

  async function synthesize() {
    if (!traj) return;
    busy = 'در حال سنتز مسیر برنده…';
    error = null;
    renderTree();
    try {
      const res = await api.reasoningSynthesize(traj.trajectory_id);
      synthesis = res;
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderTree();
    }
  }

  const treePane = h(
    'div',
    { class: 'thinking-pane' },
    h(
      'div',
      { class: 'voice-toolbar' },
      goalInput,
      h(
        'button',
        { class: 'btn btn-primary', onclick: plan },
        h('span', { html: ic('brain') }),
        'شروع درخت',
      ),
    ),
    h(
      'span',
      { class: 'chip warn' },
      h('span', { class: 'dot' }),
      'فکرها را شما می‌نویسید؛ ارزیاب قاعده‌محور است (طول/انسجام/عمق) — نه LLM',
    ),
    treeStage,
  );

  // ════════════════ tab 2: mental model (dialectic graph) ═════════════════
  let snapshot = null;
  let tensions = [];
  let queryResult = null;

  const beliefInput = h('input', {
    class: 'input',
    placeholder: 'باور یا ترجیح — مثلاً: پاسخ‌های کوتاه را ترجیح می‌دهم',
  });
  const domainInput = h('input', {
    class: 'input',
    placeholder: 'حوزه (اختیاری)',
    value: 'general',
  });
  const queryInput = h('input', { class: 'input', placeholder: 'جستجو در باورها…' });
  const modelStage = h('div', { class: 'thinking-stage' });

  function beliefRow(b) {
    const st = BELIEF_STATUS_FA[b.status] || { label: b.status || '—', cls: '' };
    return h(
      'div',
      { class: 'web-draft' },
      h(
        'div',
        { class: 'files-row' },
        h('span', { class: 'files-row-ic', html: ic('db') }),
        h(
          'div',
          { class: 'files-row-main' },
          h('span', { class: 'files-row-name', text: b.statement || '—' }),
          h('span', {
            class: 'files-row-meta mono',
            text: `${b.domain || '—'} · اطمینان ${Number(b.confidence ?? 0).toFixed(2)}`,
          }),
        ),
        h('span', { class: `chip ${st.cls}` }, h('span', { class: 'dot' }), st.label),
      ),
    );
  }

  function tensionCard(t) {
    if (t.resolved) {
      return h('div', { class: 'notice ok' }, `تناقض حل‌شده: ${t.resolution_notes || '—'}`);
    }
    const reconcileInput = h('input', {
      class: 'input',
      placeholder: 'بیانیهٔ دقیق‌تر و بالاتر که هر دو طرف را در بر می‌گیرد…',
    });
    const reconcileBtn = h(
      'button',
      {
        class: 'btn btn-primary btn-sm',
        disabled: true,
        onclick: async () => {
          const statement = reconcileInput.value.trim();
          if (!statement) return;
          try {
            await api.dialecticReconcile(t.tension_id, statement);
            await loadModel();
          } catch (e) {
            error = msg(e);
            renderModel();
          }
        },
      },
      h('span', { html: ic('check') }),
      'آشتی دادن با بیانیهٔ من',
    );
    reconcileInput.addEventListener('input', () => {
      reconcileBtn.disabled = !reconcileInput.value.trim();
    });
    return h(
      'div',
      { class: 'result-panel card wb-approval' },
      h('span', { class: 'micro', text: 'TENSION' }),
      h('span', { class: 'empty-title', text: t.description || 'تناقض' }),
      reconcileInput,
      h('div', { class: 'voice-actions' }, reconcileBtn),
    );
  }

  function renderModel() {
    const children = [];
    if (error) children.push(notice(error));
    if (!snapshot && !error) {
      children.push(h('div', { class: 'muted', text: 'در حال خواندن مدل ذهنی…' }));
    }
    if (snapshot) {
      children.push(
        h(
          'div',
          { class: 'result-meta' },
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `${snapshot.nodes_count ?? 0} باور`,
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `${snapshot.tensions_count ?? 0} تناقض`,
          ),
          h(
            'span',
            { class: `chip ${snapshot.unresolved_tensions ? 'warn' : 'ok'}` },
            h('span', { class: 'dot' }),
            `${snapshot.unresolved_tensions ?? 0} حل‌نشده`,
          ),
        ),
      );
      const beliefs = snapshot.top_beliefs || [];
      if (beliefs.length) {
        children.push(h('div', { class: 'files-list card' }, ...beliefs.map(beliefRow)));
      } else {
        children.push(
          h(
            'div',
            { class: 'voice-drop card' },
            h('span', { class: 'voice-drop-ic', html: ic('db') }),
            h('span', { class: 'empty-title', text: 'هنوز باوری ثبت نشده است' }),
            h('span', {
              class: 'empty-note',
              text: 'باورها و ترجیح‌های خود را ثبت کنید؛ دریم تناقض‌هایشان را پیدا می‌کند و شما آن‌ها را آشتی می‌دهید.',
            }),
          ),
        );
      }
      if (tensions.length) {
        children.push(
          h('span', { class: 'micro', text: 'TENSIONS' }),
          ...tensions.map(tensionCard),
        );
      }
      if (queryResult) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'QUERY RESULTS' }),
            queryResult.length
              ? h('div', { class: 'files-list' }, ...queryResult.map(beliefRow))
              : h('span', { class: 'empty-note', text: 'چیزی پیدا نشد.' }),
          ),
        );
      }
    }
    modelStage.replaceChildren(...children);
  }

  async function loadModel() {
    try {
      const snap = await api.dialecticSnapshot();
      snapshot = snap;
      const t = await api.dialecticTensions();
      tensions = t?.tensions ?? [];
      error = null;
    } catch (e) {
      snapshot = null;
      error = msg(e);
    }
    renderModel();
  }

  async function addBelief() {
    const statement = beliefInput.value.trim();
    if (!statement) return;
    try {
      await api.dialecticAdd(domainInput.value.trim() || 'general', statement);
      beliefInput.value = '';
      await loadModel();
    } catch (e) {
      error = msg(e);
      renderModel();
    }
  }

  async function detect() {
    try {
      const res = await api.dialecticTensions();
      tensions = res?.tensions ?? [];
      await loadModel();
    } catch (e) {
      error = msg(e);
      renderModel();
    }
  }

  async function query() {
    const q = queryInput.value.trim();
    if (!q) return;
    try {
      const res = await api.dialecticQuery(q);
      queryResult = res?.beliefs ?? [];
      renderModel();
    } catch (e) {
      error = msg(e);
      renderModel();
    }
  }

  const modelPane = h(
    'div',
    { class: 'thinking-pane hidden' },
    h(
      'div',
      { class: 'voice-toolbar' },
      beliefInput,
      domainInput,
      h(
        'button',
        { class: 'btn btn-primary', onclick: addBelief },
        h('span', { html: ic('plus') }),
        'ثبت باور',
      ),
      h(
        'button',
        { class: 'btn', onclick: detect },
        h('span', { html: ic('search') }),
        'تشخیص تناقض',
      ),
    ),
    h(
      'div',
      { class: 'voice-toolbar' },
      queryInput,
      h('button', { class: 'btn', onclick: query }, h('span', { html: ic('search') }), 'جستجو'),
    ),
    h(
      'span',
      { class: 'chip warn' },
      h('span', { class: 'dot' }),
      'تشخیص تناقض قاعده‌محور است (جفت‌واژه‌های متضاد) — آشتی‌سازی با بیانیهٔ خود شما',
    ),
    modelStage,
  );

  // ════════════════ tabs ══════════════════════════════════════════════════
  const treeTab = h(
    'button',
    { class: 'voice-tab active', onclick: () => switchMode('tree') },
    h('span', { html: ic('brain') }),
    'درخت استدلال',
  );
  const modelTab = h(
    'button',
    { class: 'voice-tab', onclick: () => switchMode('model') },
    h('span', { html: ic('db') }),
    'مدل ذهنی',
  );

  function switchMode(next) {
    mode = next;
    treeTab.classList.toggle('active', mode === 'tree');
    modelTab.classList.toggle('active', mode === 'model');
    treePane.classList.toggle('hidden', mode !== 'tree');
    modelPane.classList.toggle('hidden', mode !== 'model');
    if (mode === 'model' && !snapshot && !error) loadModel();
  }

  root.append(
    h(
      'div',
      { class: 'thinking-view' },
      h('div', { class: 'voice-tabs' }, treeTab, modelTab),
      treePane,
      modelPane,
    ),
  );

  renderTree();
  renderModel();
}
