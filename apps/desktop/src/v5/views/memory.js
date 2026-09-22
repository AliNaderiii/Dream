/**
 * Memory — the agent's durable memory, fully wired:
 * episodic.get_hierarchy_stats (tier counts) + episodic.query_timeline.
 * Hermes' "Remember", but transparent and inspectable.
 */

import { h, fmtTime } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const TIERS = [
  { key: 'l0', name: 'L0', note: 'خام — رویدادهای لحظه‌ای' },
  { key: 'l1', name: 'L1', note: 'نشست — خلاصه هر گفتگو' },
  { key: 'l2', name: 'L2', note: 'دانش — واقعیت‌های تثبیت‌شده' },
  { key: 'l3', name: 'L3', note: 'هویت — باورها و ترجیحات' },
];

export function memoryView(root) {
  const stats = {};
  const tierHost = h('div', { class: 'memory-tiers' });
  const results = h('div', { class: 'memory-results' });
  const queryInput = h('input', {
    class: 'input data-question',
    placeholder: 'جست‌وجو در حافظه… مثلاً: درباره پروژه پونیشا چه می‌دانی؟',
    onkeydown: (e) => {
      if (e.key === 'Enter') search();
    },
  });

  function tierCount(key) {
    // Defensive: hierarchy stats payload shape varies — find a number for the tier.
    const direct = stats[key] ?? stats[key.toUpperCase()] ?? stats?.tiers?.[key];
    if (typeof direct === 'number') return direct;
    if (direct && typeof direct === 'object' && 'count' in direct) return direct.count;
    return null;
  }

  function renderTiers() {
    tierHost.replaceChildren(
      ...TIERS.map((t) =>
        h(
          'div',
          { class: 'memory-tier card' },
          h('span', { class: 'memory-tier-name mono', text: t.name }),
          h(
            'div',
            { class: 'memory-tier-main' },
            h('span', { class: 'memory-tier-note', text: t.note }),
            h('span', {
              class: 'memory-tier-count mono',
              text: tierCount(t.key) === null ? '—' : String(tierCount(t.key)),
            }),
          ),
        ),
      ),
    );
  }

  async function loadStats() {
    try {
      Object.assign(stats, await api.episodicStats());
      renderTiers();
    } catch {
      renderTiers(); // tiers stay '—' with the honest chip below
    }
  }

  async function search() {
    const q = queryInput.value.trim();
    if (!q) return;
    results.replaceChildren(
      h('div', { class: 'notice', html: ic('refresh') }, 'در حال جست‌وجو در خط زمانی…'),
    );
    try {
      const res = await api.episodicQuery(q);
      const events = Array.isArray(res?.events) ? res.events : Array.isArray(res) ? res : [];
      if (events.length === 0) {
        results.replaceChildren(
          h(
            'div',
            { class: 'empty empty-sm' },
            h('span', { html: ic('db') }),
            h('span', { class: 'empty-title', text: 'چیزی یافت نشد' }),
            h('span', {
              class: 'empty-note',
              text: 'حافظه با استفاده از اپ خالی است — هر گفتگو و کار ایجنت اینجا جمع می‌شود.',
            }),
          ),
        );
        return;
      }
      results.replaceChildren(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'TIMELINE' }),
          ...events.slice(0, 30).map((ev) =>
            h(
              'div',
              { class: 'log-row' },
              h('span', {
                class: 'log-time mono',
                text: ev.ts ? fmtTime(ev.ts * 1000) : (ev.jalali ?? '—'),
              }),
              h('span', { class: 'log-kind', text: ev.speaker ?? ev.kind ?? 'رویداد' }),
              h('span', { class: 'log-detail', text: ev.text ?? ev.summary ?? '—' }),
            ),
          ),
        ),
      );
    } catch (e) {
      results.replaceChildren(h('div', { class: 'notice err', html: ic('alert') }, msg(e)));
    }
  }

  root.append(
    h(
      'div',
      { class: 'memory-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h(
          'div',
          { class: 'data-ask-row' },
          queryInput,
          h(
            'button',
            { class: 'btn btn-primary', onclick: search },
            h('span', { html: ic('search') }),
            'یادآوری',
          ),
        ),
        h(
          'div',
          { class: 'data-ask-meta' },
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            'خط زمانی جلالی + سلسله‌مراتب L0..L3',
          ),
          h('span', {
            class: 'faint data-hint',
            text: 'هر چیزی که ایجنت یاد می‌گیرد روی سیستم خودتان می‌ماند و قابل بازبینی است.',
          }),
        ),
      ),
      tierHost,
      results,
    ),
  );

  renderTiers();
  loadStats();
}
