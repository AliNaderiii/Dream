/**
 * Document tool — image/PDF → Persian OCR → shaped PDF report.
 * Fully wired to the core: ocr.extract / ocr.extract_invoice + pdf.export_report.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, pdfSiblingPath, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const DOC_TYPES = [
  { id: 'general', label: 'عمومی' },
  { id: 'invoice', label: 'فاکتور' },
  { id: 'receipt', label: 'رسید' },
  { id: 'id_card', label: 'کارت شناسایی' },
];

export function documentView(root, ctx) {
  let file = null;
  let docType = 'general';
  let extraction = null;
  let pdfResult = null;

  const list = h('div', { class: 'doc-list' });
  const stage = h('div', { class: 'doc-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic('alert') }, text);
  }

  function fieldsTable(fields) {
    const entries = Object.entries(fields ?? {});
    if (entries.length === 0) return null;
    return h('div', { class: 'result-panel card' },
      h('span', { class: 'micro', text: 'FIELDS' }),
      h('table', { class: 'evidence-table' },
        h('tbody',
          ...entries.map(([k, v]) =>
            h('tr', {},
              h('th', { text: k }),
              h('td', { text: typeof v === 'object' ? JSON.stringify(v) : String(v) }))))));
  }

  function renderStage({ busy = '', error = null } = {}) {
    if (!file) {
      stage.replaceChildren(
        h('div', { class: 'empty doc-empty' },
          h('span', { html: ic('upload') }),
          h('span', { class: 'empty-title', text: 'سندی انتخاب نشده' }),
          h('span', { class: 'empty-note', text: 'یک تصویر یا PDF فارسی اضافه کنید تا متن آن استخراج شود — فاکتور، قرارداد، نامه، اسکرین‌شات.' })),
      );
      return;
    }
    const children = [
      h('div', { class: 'doc-file card' },
        h('span', { class: 'doc-file-ic', html: ic('file') }),
        h('div', { class: 'doc-file-main' },
          h('span', { class: 'doc-file-name', text: file.name }),
          h('span', { class: 'doc-file-meta mono', text: `${fmtBytes(file.size)} · ${file.path}` }))),
      h('div', { class: 'doc-actions' },
        h('div', { class: 'doc-type-row' },
          h('span', { class: 'faint', text: 'نوع سند:' }),
          ...DOC_TYPES.map((t) =>
            h('button', {
              class: `btn btn-sm doc-type${docType === t.id ? ' active' : ''}`,
              onclick: (e) => {
                docType = t.id;
                for (const el of stage.querySelectorAll('.doc-type')) el.classList.remove('active');
                e.currentTarget.classList.add('active');
              },
            }, t.label))),
        h('button', {
          class: 'btn btn-primary',
          disabled: !!busy,
          onclick: extract,
        }, h('span', { html: ic('doc') }), busy === 'ocr' ? 'در حال استخراج…' : 'استخراج متن (OCR)'),
        h('button', {
          class: 'btn',
          disabled: !!busy || !extraction,
          onclick: exportPdf,
        }, h('span', { html: ic('file') }), busy === 'pdf' ? 'در حال ساخت…' : 'گزارش PDF فارسی')),
    ];
    if (error) children.push(notice(error));
    if (extraction) {
      const text = extraction.text ?? extraction.full_text ?? '';
      if (text) {
        children.push(
          h('div', { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'EXTRACTED TEXT' }),
            h('div', { class: 'result-text', text })),
        );
      }
      const fields = extraction.fields ?? extraction.invoice_fields;
      if (fields) children.push(fieldsTable(fields));
      if (!text && !fields) {
        children.push(notice('هیچ متنی استخراج نشد — سند شاید خالی یا ناخواناست.', 'warn'));
      }
    }
    if (pdfResult?.success) {
      children.push(h('div', { class: 'notice ok', html: ic('check') },
        `PDF ساخته شد: ${pdfResult.file_path} (${fmtBytes(pdfResult.bytes ?? 0)})`));
    }
    stage.replaceChildren(...children);
  }

  async function extract() {
    renderStage({ busy: 'ocr' });
    try {
      const res = docType === 'invoice' ? await api.ocrInvoice(file.path) : await api.ocrExtract(file.path, docType);
      if (res?.success === false) {
        extraction = null;
        renderStage({ error: res.error || 'استخراج ناموفق بود' });
        return;
      }
      extraction = res;
      pdfResult = null;
      renderStage();
    } catch (e) {
      extraction = null;
      renderStage({ error: msg(e) });
    }
  }

  async function exportPdf() {
    renderStage({ busy: 'pdf' });
    try {
      const text = extraction.text ?? extraction.full_text ?? '';
      const fields = extraction.fields ?? extraction.invoice_fields ?? {};
      const report = {
        title: 'استخراج متن سند',
        subtitle: file.name,
        sections: [
          {
            heading: 'متن استخراج‌شده',
            paragraphs: text ? [text] : ['—'],
            kpis: [
              { label: 'نوع سند', value: docType },
              { label: 'طول متن', value: `${text.length} نویسه` },
            ],
            ...(Object.keys(fields).length
              ? { table: { columns: ['فیلد', 'مقدار'], rows: Object.entries(fields).map(([k, v]) => [k, String(v)]) } }
              : {}),
          },
        ],
      };
      pdfResult = await api.pdfExport(report, pdfSiblingPath(file.path, 'report'));
      renderStage();
      ctx.openEvidence({
        title: 'گزارش استخراج سند',
        steps: [
          { name: 'سند', detail: file.name, meta: fmtBytes(file.size) },
          { name: `ocr.extract (${docType})`, detail: `${text.length} نویسه`, meta: 'هسته پایتون' },
          { name: 'pdf.export_report', detail: pdfResult.file_path, meta: fmtBytes(pdfResult.bytes ?? 0) },
        ],
      });
    } catch (e) {
      pdfResult = null;
      renderStage({ error: msg(e) });
    }
  }

  async function choose() {
    try {
      const entry = await pickFile('انتخاب تصویر یا PDF');
      if (!entry) return;
      file = entry;
      extraction = null;
      pdfResult = null;
      list.append(
        h('button', {
          class: 'doc-item card active',
          onclick: (e) => {
            for (const el of list.querySelectorAll('.doc-item')) el.classList.remove('active');
            e.currentTarget.classList.add('active');
          },
        },
          h('span', { class: 'doc-item-ic', html: ic('file') }),
          h('div', { class: 'doc-item-main' },
            h('span', { class: 'doc-item-name', text: entry.name }),
            h('span', { class: 'doc-item-meta mono', text: fmtBytes(entry.size) }))),
      );
      renderStage();
    } catch (e) {
      renderStage({ error: msg(e) });
    }
  }

  root.append(
    h('div', { class: 'doc-view' },
      h('aside', { class: 'doc-side' },
        h('span', { class: 'micro', text: 'DOCUMENTS' }),
        h('button', { class: 'btn add-doc', onclick: choose }, h('span', { html: ic('plus') }), 'افزودن سند'),
        list,
        h('span', { class: 'faint doc-side-note', text: 'فایل‌ها فقط روی سیستم شما می‌مانند.' })),
      stage),
  );

  renderStage();
}
