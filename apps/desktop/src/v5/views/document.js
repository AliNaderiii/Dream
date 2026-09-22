/**
 * Document tool — image/PDF → Persian OCR → shaped PDF report.
 * Phase 1: full layout and honest empty/disabled states; the real
 * `ocr.extract` / `pdf.export_report` calls land in phase 2.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

let selected = null; // { name, size }

export function documentView(root, ctx) {
  const list = h('div', { class: 'doc-list' });
  const stage = h('div', { class: 'doc-stage' });

  function renderStage() {
    if (!selected) {
      stage.replaceChildren(
        h(
          'div',
          { class: 'empty doc-empty' },
          h('span', { html: ic('upload') }),
          h('span', { class: 'empty-title', text: 'سندی انتخاب نشده' }),
          h('span', { class: 'empty-note', text: 'یک تصویر یا PDF فارسی اضافه کنید تا متن آن استخراج شود — فاکتور، قرارداد، نامه، اسکرین‌شات.' }),
        ),
      );
      return;
    }
    stage.replaceChildren(
      h(
        'div',
        { class: 'doc-file card' },
        h('span', { class: 'doc-file-ic', html: ic('file') }),
        h('div', { class: 'doc-file-main' },
          h('span', { class: 'doc-file-name', text: selected.name }),
          h('span', { class: 'doc-file-meta mono', text: fmtBytes(selected.size) }),
        ),
      ),
      h(
        'div',
        { class: 'doc-actions' },
        h('button', { class: 'btn', disabled: true, title: 'فاز ۲ — اتصال به هسته' }, h('span', { html: ic('doc') }), 'استخراج متن (OCR)'),
        h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — اتصال به هسته' }, h('span', { html: ic('file') }), 'گزارش PDF فارسی'),
      ),
      h('div', { class: 'notice', html: ic('alert') },
        'در این اسکلت طراحی، پردازش هنوز به هسته وصل نشده — در فاز ۲ همان فایل به ocr.extract واقعی ارسال می‌شود.'),
    );
  }

  function addFile(file) {
    selected = { name: file.name, size: file.size };
    list.append(
      h(
        'button',
        {
          class: 'doc-item card' + (selected ? ' active' : ''),
          onclick: (e) => {
            for (const el of list.querySelectorAll('.doc-item')) el.classList.remove('active');
            e.currentTarget.classList.add('active');
          },
        },
        h('span', { class: 'doc-item-ic', html: ic('file') }),
        h('div', { class: 'doc-item-main' },
          h('span', { class: 'doc-item-name', text: file.name }),
          h('span', { class: 'doc-item-meta mono', text: fmtBytes(file.size) }),
        ),
      ),
    );
    renderStage();
  }

  const fileInput = h('input', {
    type: 'file',
    accept: 'image/*,application/pdf',
    style: 'display:none',
    onchange: (e) => {
      const file = e.target.files?.[0];
      if (file) addFile(file);
    },
  });

  root.append(
    h(
      'div',
      { class: 'doc-view' },
      h(
        'aside',
        { class: 'doc-side' },
        h('span', { class: 'micro', text: 'DOCUMENTS' }),
        h('button', { class: 'btn add-doc', onclick: () => fileInput.click() }, h('span', { html: ic('plus') }), 'افزودن سند'),
        list,
        fileInput,
        h('span', { class: 'faint doc-side-note', text: 'فایل‌ها فقط روی سیستم شما می‌مانند.' }),
      ),
      stage,
    ),
  );

  renderStage();
}
