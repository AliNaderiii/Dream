/**
 * Runtimes — the provider-hubs matrix, straight from the real core:
 *  - the active route (hosted → aval → ollama → byok → echo), resolved
 *    deterministically and offline by the router;
 *  - the six local runtimes with honest detection/health chips, bounded
 *    probes (no secrets are ever sent), real model listings and a
 *    persisted model selection;
 *  - the optional tool gateway — tokens live in the OS keychain and are
 *    refused over RPC by design;
 *  - the provider catalog (local + cloud) with search.
 * Zero simulations: if the core is unreachable, everything says so.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const HEALTH_FA = {
  idle: { label: 'بیکار', cls: '' },
  healthy: { label: 'سالم', cls: 'ok' },
  down: { label: 'قطع', cls: 'err' },
};

const TOOLCALL_FA = {
  native: { label: 'ابزار بومی', cls: 'ok' },
  disabled: { label: 'بدون ابزار', cls: 'warn' },
  fallback: { label: 'پشتیبان عمومی', cls: 'warn' },
};

const chip = (label, cls = '') =>
  h('span', { class: `chip ${cls}`.trim() }, h('span', { class: 'dot' }), label);

export function runtimesView(root, ctx) {
  let error = null;
  let busy = '';
  let route = null; // {priority, active, sentence_fa}
  let runtimes = []; // runtime records from providerhubs.runtimes
  let gateway = null; // gateway snapshot
  let catalog = [];
  let catalogCount = 0;
  const details = {}; // runtime_id → { test, models, diagnose, busy, err }

  // ── status (error / busy) ────────────────────────────────────────────────
  const statusHost = h('div', { class: 'rt-status' });

  function renderStatus() {
    const rows = [];
    if (error) rows.push(h('div', { class: 'notice err', html: ic('alert') }, error));
    if (busy) rows.push(h('div', { class: 'notice', html: ic('refresh') }, busy));
    statusHost.replaceChildren(...rows);
  }

  // ── route ────────────────────────────────────────────────────────────────
  const routeHost = h('div', {});

  function renderRoute() {
    if (!route) {
      routeHost.replaceChildren(
        h('span', { class: 'muted', text: 'مسیر فعال از هسته خوانده می‌شود…' }),
      );
      return;
    }
    const chain = [];
    for (const [i, step] of (route.priority || []).entries()) {
      if (i > 0) chain.push(h('span', { class: 'route-sep', text: '→' }));
      chain.push(chip(step, step === route.active ? 'ok' : ''));
    }
    routeHost.replaceChildren(
      h(
        'div',
        { class: 'route-active' },
        h('span', { class: 'muted', text: 'مسیر فعال:' }),
        h('span', { class: 'chip ok' }, h('span', { class: 'dot' }), route.active),
      ),
      h('div', { class: 'route-chain', dir: 'ltr' }, ...chain),
      h('span', { class: 'muted route-sentence', text: route.sentence_fa || '' }),
    );
  }

  // ── runtime matrix ───────────────────────────────────────────────────────
  const matrixHost = h('div', { class: 'rt-matrix' });

  function runtimeCard(rt) {
    const d = details[rt.id] || {};
    const health = HEALTH_FA[rt.health] || { label: rt.health || '—', cls: '' };
    const tools = TOOLCALL_FA[rt.tool_calling] || { label: rt.tool_calling || '—', cls: '' };

    const resultRows = [];
    if (d.busy) resultRows.push(h('div', { class: 'notice', html: ic('refresh') }, d.busy));
    if (d.err) resultRows.push(h('div', { class: 'notice err', html: ic('alert') }, d.err));

    if (d.test) {
      const t = d.test;
      resultRows.push(
        h(
          'div',
          { class: 'rt-result' },
          chip(t.ok ? `اتصال برقرار — ${t.latency_ms}ms` : 'پاسخ نداد', t.ok ? 'ok' : 'err'),
          h('span', { class: 'muted rt-detail', text: t.detail || '' }),
          h(
            'button',
            {
              class: 'btn btn-ghost btn-sm',
              onclick: () =>
                ctx.openEvidence({
                  title: `پروب ${rt.name}`,
                  steps: [
                    {
                      name: 'providerhubs.test',
                      detail: `runtime_id: ${rt.id}`,
                      meta: 'پروب محدود — بدون ارسال رمز',
                    },
                    {
                      name: 'نتیجه',
                      detail: `ok: ${t.ok} · latency_ms: ${t.latency_ms}`,
                      meta: t.detail || '',
                    },
                  ],
                }),
            },
            'شواهد',
          ),
        ),
      );
    }

    if (d.diagnose) {
      const g = d.diagnose;
      resultRows.push(
        h(
          'div',
          { class: 'rt-result' },
          chip(
            g.firing ? 'فراخوانی ابزار آماده است' : 'فراخوانی ابزار فعال نیست',
            g.firing ? 'ok' : 'warn',
          ),
          h('span', { class: 'muted rt-detail', text: g.reason_fa || g.reason || '' }),
          g.fix_fa ? h('span', { class: 'muted rt-detail', text: `راه‌حل: ${g.fix_fa}` }) : null,
          g.reduced_reliability
            ? h('span', {
                class: 'muted rt-detail',
                text: 'قابلیت اطمینان کمتر — تجزیه‌گر پشتیبان',
              })
            : null,
        ),
      );
    }

    if (d.models) {
      const selected = d.models.selected_model || '';
      const list = d.models.models || [];
      resultRows.push(
        h(
          'div',
          { class: 'rt-models' },
          list.length === 0
            ? h('span', {
                class: 'muted',
                text: 'مدلی برنگشت — سرور را روشن کنید و دوباره بگیرید.',
              })
            : list.map((m) =>
                h(
                  'button',
                  {
                    class: `model-row${m === selected ? ' selected' : ''}`,
                    dir: 'ltr',
                    onclick: () => doSelect(rt, m),
                  },
                  h('span', { class: 'mono model-name', text: m }),
                  m === selected
                    ? chip('انتخاب‌شده', 'ok')
                    : h('span', { class: 'muted model-hint', text: 'برای انتخاب کلیک کنید' }),
                ),
              ),
        ),
      );
    }

    return h(
      'div',
      { class: 'runtime-card card', dataset: { runtime: rt.id } },
      h(
        'div',
        { class: 'runtime-head' },
        h(
          'div',
          { class: 'runtime-title' },
          h('span', { class: 'runtime-name', text: rt.name || rt.id }),
          rt.recommended ? chip('پیشنهادی', 'ok') : null,
        ),
        h('span', { class: 'mono runtime-endpoint', dir: 'ltr', text: rt.endpoint || '—' }),
      ),
      h(
        'div',
        { class: 'runtime-chips' },
        chip(rt.detected ? 'در دسترس' : 'پیدا نشد', rt.detected ? 'ok' : ''),
        chip(health.label, health.cls),
        chip(tools.label, tools.cls),
        chip('محلی', 'ok'),
      ),
      rt.selected_model
        ? h('span', {
            class: 'mono runtime-model',
            dir: 'ltr',
            text: `مدل انتخابی: ${rt.selected_model}`,
          })
        : null,
      h('span', { class: 'muted runtime-privacy', text: rt.privacy_fa || '' }),
      h(
        'div',
        { class: 'runtime-actions' },
        h('button', { class: 'btn btn-sm', onclick: () => doTest(rt) }, 'تست اتصال'),
        h('button', { class: 'btn btn-sm', onclick: () => doModels(rt) }, 'مدل‌ها'),
        h('button', { class: 'btn btn-sm', onclick: () => doDiagnose(rt) }, 'تشخیص'),
      ),
      ...resultRows,
    );
  }

  function renderMatrix() {
    if (runtimes.length === 0) {
      matrixHost.replaceChildren(
        h('span', { class: 'muted', text: 'ماتریس موتورها از هسته خوانده می‌شود…' }),
      );
      return;
    }
    matrixHost.replaceChildren(...runtimes.map(runtimeCard));
  }

  async function doTest(rt) {
    const d = (details[rt.id] = details[rt.id] || {});
    d.busy = 'پروب محدود در حال اجراست…';
    d.err = null;
    d.test = null;
    renderMatrix();
    try {
      d.test = await api.phTest(rt.id);
      try {
        const r = await api.phRuntimes();
        runtimes = r?.runtimes || [];
      } catch {
        /* health chip refresh is best-effort; the probe result is shown */
      }
    } catch (e) {
      d.err = msg(e);
    } finally {
      d.busy = '';
      renderMatrix();
    }
  }

  async function doModels(rt) {
    const d = (details[rt.id] = details[rt.id] || {});
    d.busy = 'در حال گرفتن فهرست مدل‌ها…';
    d.err = null;
    d.models = null;
    renderMatrix();
    try {
      d.models = await api.phModels(rt.id);
    } catch (e) {
      d.err = msg(e);
    } finally {
      d.busy = '';
      renderMatrix();
    }
  }

  async function doDiagnose(rt) {
    const d = (details[rt.id] = details[rt.id] || {});
    d.busy = 'در حال تشخیص…';
    d.err = null;
    d.diagnose = null;
    renderMatrix();
    try {
      d.diagnose = await api.phDiagnose(rt.id);
    } catch (e) {
      d.err = msg(e);
    } finally {
      d.busy = '';
      renderMatrix();
    }
  }

  async function doSelect(rt, model) {
    const d = (details[rt.id] = details[rt.id] || {});
    d.busy = 'در حال ثبت انتخاب مدل…';
    d.err = null;
    renderMatrix();
    try {
      const rec = await api.phSelectModel(rt.id, model);
      runtimes = runtimes.map((r) => (r.id === rec.id ? rec : r));
      if (d.models) d.models = { ...d.models, selected_model: model };
    } catch (e) {
      d.err = msg(e);
    } finally {
      d.busy = '';
      renderMatrix();
    }
  }

  // ── tool gateway ─────────────────────────────────────────────────────────
  const gwHost = h('div', {});

  function renderGateway() {
    if (!gateway) {
      gwHost.replaceChildren(
        h('span', { class: 'muted', text: 'وضعیت گیت‌وی از هسته خوانده می‌شود…' }),
      );
      return;
    }
    gwHost.replaceChildren(
      h(
        'div',
        { class: 'gw-head' },
        chip(gateway.enabled ? 'گیت‌وی روشن' : 'گیت‌وی خاموش', gateway.enabled ? 'ok' : ''),
        chip(
          gateway.auth === 'keychain' ? 'توکن در keychain سیستم' : 'بدون توکن',
          gateway.auth === 'keychain' ? 'ok' : 'warn',
        ),
        h(
          'button',
          {
            class: 'btn btn-sm',
            onclick: async () => {
              try {
                gateway = await api.phGatewayUpdate({ enabled: !gateway.enabled });
              } catch (e) {
                error = msg(e);
              }
              renderGateway();
              renderStatus();
            },
          },
          gateway.enabled ? 'خاموش‌کردن گیت‌وی' : 'روشن‌کردن گیت‌وی',
        ),
      ),
      h(
        'div',
        { class: 'gw-tools' },
        ...(gateway.tools || []).map((tool) =>
          h(
            'div',
            { class: 'gw-tool' },
            h('span', { class: 'mono gw-tool-id', dir: 'ltr', text: tool.id }),
            chip(tool.enabled ? 'فعال' : 'خاموش', tool.enabled ? 'ok' : ''),
            chip(
              tool.credential_configured ? 'توکن موجود' : 'بدون توکن',
              tool.credential_configured ? 'ok' : 'warn',
            ),
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  try {
                    gateway = await api.phGatewayUpdate({
                      tool_id: tool.id,
                      tool_enabled: !tool.enabled,
                    });
                  } catch (e) {
                    error = msg(e);
                  }
                  renderGateway();
                  renderStatus();
                },
              },
              tool.enabled ? 'خاموش' : 'روشن',
            ),
          ),
        ),
      ),
    );
  }

  // ── catalog ──────────────────────────────────────────────────────────────
  const catSearch = h('input', {
    class: 'input cat-search',
    dir: 'ltr',
    placeholder: 'جستجو در کاتالوگ — مثلاً ollama',
  });
  const catHost = h('div', { class: 'rt-catalog' });

  function catalogRow(entry) {
    return h(
      'div',
      { class: 'cat-row' },
      h(
        'div',
        { class: 'cat-main' },
        h('span', { class: 'cat-name', text: entry.name || entry.id }),
        h('span', { class: 'muted cat-notes', text: entry.notes || '' }),
      ),
      h(
        'div',
        { class: 'cat-chips' },
        chip(entry.local ? 'محلی' : 'ابری', entry.local ? 'ok' : 'warn'),
        chip(
          entry.data_leaves_machine ? 'داده خارج می‌رود' : 'داده روی دستگاه می‌ماند',
          entry.data_leaves_machine ? 'warn' : 'ok',
        ),
        entry.tool_calling ? chip('فراخوانی ابزار', 'ok') : null,
      ),
    );
  }

  function renderCatalog() {
    catHost.replaceChildren(
      h('span', { class: 'muted cat-count', text: `${catalogCount} ارائه‌دهنده` }),
      ...(catalog || []).map(catalogRow),
    );
  }

  let catTimer;
  catSearch.addEventListener('input', () => {
    clearTimeout(catTimer);
    catTimer = setTimeout(async () => {
      try {
        const r = await api.phCatalog(catSearch.value.trim());
        catalog = r?.catalog || [];
        catalogCount = r?.count ?? 0;
      } catch {
        catalog = [];
        catalogCount = 0;
      }
      renderCatalog();
    }, 250);
  });

  // ── load & layout ────────────────────────────────────────────────────────
  async function refresh() {
    error = null;
    busy = 'در حال خواندن ماتریس از هسته…';
    renderStatus();
    const results = await Promise.allSettled([
      api.phRoute().then((r) => {
        route = r;
        renderRoute();
      }),
      api.phRuntimes().then((r) => {
        runtimes = r?.runtimes || [];
        renderMatrix();
      }),
      api.phGateway().then((r) => {
        gateway = r;
        renderGateway();
      }),
      api.phCatalog('').then((r) => {
        catalog = r?.catalog || [];
        catalogCount = r?.count ?? 0;
        renderCatalog();
      }),
    ]);
    const failed = results.find((r) => r.status === 'rejected');
    if (failed) error = msg(failed.reason);
    busy = '';
    renderStatus();
  }

  root.append(
    h(
      'div',
      { class: 'runtimes-view' },
      statusHost,
      h(
        'div',
        { class: 'rt-toolbar' },
        h(
          'span',
          { class: 'muted rt-honesty' },
          'همهٔ داده‌ها از متدهای واقعی providerhubs.* هسته می‌آید — پروب‌ها محدودند و هرگز رمزی ارسال نمی‌شود.',
        ),
        h(
          'button',
          { class: 'btn btn-sm', onclick: () => refresh() },
          h('span', { html: ic('refresh') }),
          'به‌روزرسانی',
        ),
      ),
      section('ROUTE', 'مسیر فعال', h('div', { class: 'section-card card route-card' }, routeHost)),
      section(
        'RUNTIMES',
        'ماتریس موتورهای محلی',
        h('div', { class: 'section-card card' }, matrixHost),
      ),
      section(
        'GATEWAY',
        'گیت‌وی ابزار (اختیاری)',
        h(
          'div',
          { class: 'section-card card' },
          h('span', {
            class: 'muted gw-note',
            text: 'برای گفتگوی محلی لازم نیست. توکن فقط در keychain سیستم ذخیره می‌شود و از پل رد نمی‌شود — این طراحی هسته است.',
          }),
          gwHost,
        ),
      ),
      section(
        'CATALOG',
        'کاتالوگ ارائه‌دهنده‌ها',
        h('div', { class: 'section-card card' }, catSearch, catHost),
      ),
    ),
  );

  renderStatus();
  renderRoute();
  renderMatrix();
  renderGateway();
  renderCatalog();
  refresh();
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
