/**
 * Data tool — dataset → question → grounded answer with an evidence table
 * and KPI cards, exportable as a shaped Persian PDF (DeepAnalyze habit:
 * the answer never floats free of its evidence).
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

export function dataView(root, ctx) {
  const answer = h('div', { class: 'data-answer' });

  function renderAnswer() {
    answer.replaceChildren(
      h(
        'div',
        { class: 'empty' },
        h('span', { html: ic('chart') }),
        h('span', { class: 'empty-title', text: 'هنوز پرسشی پاسخ نگرفته' }),
        h('span', { class: 'empty-note', text: 'مجموعه‌داده را بارگذاری کنید و بپرسید؛ پاسخ همراه جدول شواهد و شاخص‌ها نمایش داده می‌شود.' }),
      ),
    );
  }

  const datasets = h('div', { class: 'data-datasets' },
    h('span', { class: 'empty empty-sm' },
      h('span', { html: ic('db') }),
      h('span', { class: 'empty-title', text: 'مجموعه‌داده‌ای بارگذاری نشده' }),
      h('span', { class: 'empty-note', text: 'CSV / JSON / SQLite — فاز ۲ از طریق data.load_data واقعی.' }),
    ),
  );

  root.append(
    h(
      'div',
      { class: 'data-view' },
      h(
        'div',
        { class: 'data-ask card' },
        h('div', { class: 'data-ask-row' },
          h('input', {
            class: 'input data-question',
            placeholder: 'مثلاً: پرفروش‌ترین محصول هر ماه کدام بوده؟',
            onkeydown: (e) => {
              if (e.key === 'Enter') e.preventDefault();
            },
          }),
          h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — اتصال به هسته' }, h('span', { html: ic('send') }), 'بپرس'),
        ),
        h('div', { class: 'data-ask-meta' },
          h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'بدون مجموعه‌داده'),
          h('span', { class: 'faint data-hint', text: 'پاسخ‌ها فقط از داده واقعی استخراج می‌شوند و منبعشان ذکر می‌شود.' }),
        ),
      ),
      datasets,
      answer,
    ),
  );

  renderAnswer();
}
