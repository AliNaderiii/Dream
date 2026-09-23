/**
 * Vision — one real action: capture the screen and extract its Persian text.
 * `vision.capture_screen` (Windows GDI) writes a temp file, OCRs it with the
 * core engine, and deletes the file immediately — screen pixels never
 * persist (P-14). Privacy note is surfaced in the UI, not buried.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFolder, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function visionView(root, ctx) {
  let result = null; // capture_screen OCR result
  let pdfResult = null;
  let pdfEvidence = null; // shown on demand — the drawer never opens itself
  let busy = '';
  let error = null;

  const stage = h('div', { class: 'vision-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, busy));

    if (!result && !busy && !error) {
      children.push(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('eye') }),
          h('span', { class: 'empty-title', text: 'از صفحه‌ی خود عکس بگیرید و متنش را بگیرید' }),
          h('span', {
            class: 'empty-note',
            text: 'کل صفحه فعلی گرفته می‌شود، با OCR فارسی هسته متن می‌شود و اسکرین‌شات بلافاصله و برای همیشه حذف می‌شود.',
          }),
          h(
            'span',
            { class: 'chip warn' },
            h('span', { class: 'dot' }),
            'حریم خصوصی: پیکسل‌های صفحه روی دیسک ذخیره نمی‌شوند',
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            'فقط داخل اپلیکیشن دسکتاپ — در پیش‌نمایش مرورگر صفحه‌ای برای گرفتن وجود ندارد',
          ),
        ),
      );
    }

    if (result) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'SCREEN TEXT' }),
          result.text
            ? h('div', { class: 'result-text', text: result.text })
            : h('span', { class: 'empty-note', text: 'متنی از صفحه استخراج نشد.' }),
          h(
            'div',
            { class: 'result-meta' },
            h(
              'span',
              { class: 'chip ok' },
              h('span', { class: 'dot' }),
              `موتور: ${result.engine || 'OCR هسته'}`,
            ),
            result.confidence != null
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `دقت: ${Math.round((result.confidence ?? 0) * 100)}%`,
                )
              : null,
            result.screen
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `صفحه ${result.screen.width ?? '—'}×${result.screen.height ?? '—'}`,
                )
              : null,
            result.text
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${result.text.length} نویسه`,
                )
              : null,
          ),
        ),
        h(
          'div',
          { class: 'voice-actions' },
          h(
            'button',
            { class: 'btn', disabled: !!busy || !result.text, onclick: exportPdf },
            h('span', { html: ic('file') }),
            busy === 'pdf' ? 'در حال ساخت…' : 'گزارش PDF فارسی',
          ),
        ),
      );
      if (pdfResult?.success) {
        children.push(
          h(
            'div',
            { class: 'notice ok', html: ic('check') },
            `PDF ساخته شد: ${pdfResult.file_path} (${fmtBytes(pdfResult.bytes ?? 0)})`,
            pdfEvidence
              ? h(
                  'button',
                  {
                    class: 'btn btn-sm evidence-link',
                    onclick: () => ctx.openEvidence(pdfEvidence),
                  },
                  h('span', { html: ic('evidence') }),
                  'شواهد',
                )
              : null,
          ),
        );
      }
    }
    stage.replaceChildren(...children);
  }

  async function capture() {
    busy = 'در حال عکس‌گرفتن از صفحه و استخراج متن…';
    error = null;
    result = null;
    pdfResult = null;
    renderStage();
    try {
      const res = await api.visionCaptureScreen('general');
      if (res?.success === false) {
        error = res.error || 'عکس‌گرفتن از صفحه ناموفق بود';
      } else {
        result = res;
      }
    } catch (e) {
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function exportPdf() {
    try {
      const folder = await pickFolder('پوشه‌ی مقصد برای گزارش PDF');
      if (!folder) return;
      busy = 'pdf';
      renderStage();
      const report = {
        title: 'متن استخراج‌شده از صفحه',
        subtitle: 'vision.capture_screen — اسکرین‌شات بلافاصله حذف شد',
        sections: [
          {
            heading: 'متن صفحه',
            paragraphs: [result.text],
            kpis: [
              { label: 'موتور', value: result.engine || 'OCR هسته' },
              { label: 'نویسه', value: String(result.text.length) },
            ],
          },
        ],
      };
      const out = `${folder.replace(/[\\/]+$/, '')}/screen-scan.report.pdf`;
      pdfResult = await api.pdfExport(report, out);
      pdfEvidence = {
        title: 'گزارش بینایی صفحه',
        steps: [
          { name: 'vision.capture_screen', detail: 'GDI + حذف فوری اسکرین‌شات', meta: 'P-14' },
          { name: 'ocr', detail: `${result.text.length} نویسه`, meta: result.engine || 'هسته' },
          {
            name: 'pdf.export_report',
            detail: pdfResult.file_path,
            meta: fmtBytes(pdfResult.bytes ?? 0),
          },
        ],
      };
    } catch (e) {
      pdfResult = null;
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  root.append(
    h(
      'div',
      { class: 'vision-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        h(
          'button',
          { class: 'btn btn-primary', onclick: capture },
          h('span', { html: ic('eye') }),
          'عکس‌گرفتن از صفحه',
        ),
      ),
      stage,
    ),
  );

  renderStage();
}
