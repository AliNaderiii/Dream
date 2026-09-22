/**
 * Research — deep research projects: question → plan → sources → draft →
 * approval → export. The Open-Science habit: nothing publishes without an
 * explicit approval step.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

const PIPELINE = [
  { name: 'برنامه', note: 'ایجنت منابع و مراحل را پیشنهاد می‌دهد' },
  { name: 'منابع', note: 'جست‌وجو و مرور وب واقعی' },
  { name: 'پیش‌نویس', note: 'نوشتن با استناد به منابع' },
  { name: 'تأیید', note: 'شما پیش از خروجی نهایی تأیید می‌کنید' },
  { name: 'خروجی', note: 'گزارش PDF فارسی با پیوند به شواهد' },
];

export function researchView(root, ctx) {
  root.append(
    h(
      'div',
      { class: 'research-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h('div', { class: 'data-ask-row' },
          h('input', {
            class: 'input data-question',
            placeholder: 'موضوع پژوهش… مثلاً: مقایسه فناوری‌های ذخیره‌سازی خورشیدی در ایران',
            onkeydown: (e) => {
              if (e.key === 'Enter') e.preventDefault();
            },
          }),
          h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — research.create' },
            h('span', { html: ic('search') }), 'شروع پژوهش')),
        h('div', { class: 'data-ask-meta' },
          h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'بدون پروژه فعال'),
          h('span', { class: 'faint data-hint', text: 'پژوهش چندمرحله‌ای با مرور وب واقعی و تأیید صریح شما در هر خروجی.' })),
      ),
      h(
        'div',
        { class: 'research-pipeline card' },
        h('span', { class: 'micro', text: 'PIPELINE' }),
        h('div', { class: 'pipeline-steps' },
          ...PIPELINE.map((s, i) =>
            h('div', { class: 'pipeline-step' },
              h('span', { class: 'pipeline-idx mono', text: String(i + 1).padStart(2, '0') }),
              h('div', { class: 'pipeline-main' },
                h('span', { class: 'pipeline-name', text: s.name }),
                h('span', { class: 'pipeline-note', text: s.note }))),
          )),
      ),
      h(
        'div',
        { class: 'empty' },
        h('span', { html: ic('search') }),
        h('span', { class: 'empty-title', text: 'پروژه پژوهشی ندارید' }),
        h('span', { class: 'empty-note', text: 'موتور پژوهش در هسته فعال است (research.create/plan/approve) — اتصال رابط در فاز ۲.' }),
      ),
    ),
  );
}
