/**
 * Memory — the agent's durable memory: events, facts, and the Jalali
 * timeline. The crown jewel of the core (episodic L0..L3 hierarchy) made
 * inspectable — Hermes' "Remember", but transparent.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

const TIERS = [
  { name: 'L0', note: 'خام — رویدادهای لحظه‌ای' },
  { name: 'L1', note: 'نشست — خلاصه هر گفتگو' },
  { name: 'L2', note: 'دانش — واقعیت‌های تثبیت‌شده' },
  { name: 'L3', note: 'هویت — باورها و ترجیحات' },
];

export function memoryView(root, ctx) {
  root.append(
    h(
      'div',
      { class: 'memory-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h('div', { class: 'data-ask-row' },
          h('input', {
            class: 'input data-question',
            placeholder: 'جست‌وجو در حافظه… مثلاً: درباره پروژه پونیشا چه می‌دانی؟',
            onkeydown: (e) => {
              if (e.key === 'Enter') e.preventDefault();
            },
          }),
          h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — episodic.query_timeline' },
            h('span', { html: ic('search') }), 'یادآوری')),
        h('div', { class: 'data-ask-meta' },
          h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'حافظه: در دسترس پس از اتصال'),
          h('span', { class: 'faint data-hint', text: 'هر چیزی که ایجنت یاد می‌گیرد روی سیستم خودتان می‌ماند و قابل بازبینی است.' })),
      ),
      h(
        'div',
        { class: 'memory-tiers' },
        ...TIERS.map((t) =>
          h('div', { class: 'memory-tier card' },
            h('span', { class: 'memory-tier-name mono', text: t.name }),
            h('div', { class: 'memory-tier-main' },
              h('span', { class: 'memory-tier-note', text: t.note }),
              h('span', { class: 'memory-tier-count mono', text: '—' })),
          )),
      ),
      h(
        'div',
        { class: 'empty' },
        h('span', { html: ic('db') }),
        h('span', { class: 'empty-title', text: 'خط زمانی خالی است' }),
        h('span', { class: 'empty-note', text: 'حافظه سلسله‌مراتبی و خط زمانی جلالی در هسته فعال است (episodic.*) — نمایش زنده در فاز ۲.' }),
      ),
    ),
  );
}
