/**
 * Voice tool — audio file → real transcription → Persian PDF.
 * Fully wired to the core: stt.transcribe + pdf.export_report.
 * The engine badge is always honest: faster-whisper (real) or a clear
 * "unavailable" state — never a fake transcript.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, pdfSiblingPath, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function voiceView(root, ctx) {
  let file = null; // FileEntry {path, name, size}
  let transcript = null; // stt result
  let pdfResult = null;

  const stage = h('div', { class: 'voice-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic('alert') }, text);
  }

  function engineChip() {
    if (!transcript) {
      return h(
        'span',
        { class: 'chip voice-engine-chip' },
        h('span', { class: 'dot' }),
        'موتور رونویسی: نامشخص',
      );
    }
    if (transcript.simulated) {
      return h(
        'span',
        { class: 'chip warn voice-engine-chip' },
        h('span', { class: 'dot' }),
        `موتور داخلی (${transcript.engine || 'built-in'})`,
      );
    }
    return h(
      'span',
      { class: 'chip ok voice-engine-chip' },
      h('span', { class: 'dot' }),
      transcript.engine || 'faster-whisper',
    );
  }

  function renderStage({ busy = '', error = null } = {}) {
    const children = [];
    if (!file) {
      children.push(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('mic') }),
          h('span', { class: 'empty-title', text: 'فایل صوتی انتخاب کنید' }),
          h('span', {
            class: 'empty-note',
            text: 'OGG/Opus (ویس تلگرام)، WAV، MP3 یا M4A — حداکثر ۲۵ مگابایت',
          }),
          engineChip(),
        ),
      );
    } else {
      children.push(
        h(
          'div',
          { class: 'voice-file card' },
          h('span', { class: 'voice-file-ic', html: ic('wave') }),
          h(
            'div',
            { class: 'voice-file-main' },
            h('span', { class: 'voice-file-name', text: file.name }),
            h('span', {
              class: 'voice-file-meta mono',
              text: `${fmtBytes(file.size)} · ${file.path}`,
            }),
          ),
          engineChip(),
        ),
      );
      children.push(
        h(
          'div',
          { class: 'voice-actions' },
          h(
            'button',
            {
              class: 'btn btn-primary',
              disabled: !!busy,
              onclick: transcribe,
            },
            h('span', { html: ic('wave') }),
            busy === 'stt' ? 'در حال رونویسی…' : 'رونویسی',
          ),
          h(
            'button',
            {
              class: 'btn',
              disabled: !!busy || !transcript?.text,
              title: 'خروجی PDF فارسی با حروف متصل',
              onclick: exportPdf,
            },
            h('span', { html: ic('file') }),
            busy === 'pdf' ? 'در حال ساخت…' : 'گزارش PDF فارسی',
          ),
        ),
      );
      if (error) children.push(notice(error));
      if (transcript?.text) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'TRANSCRIPT' }),
            h('div', { class: 'result-text', text: transcript.text }),
            h(
              'div',
              { class: 'result-meta' },
              h(
                'span',
                { class: 'chip' },
                h('span', { class: 'dot' }),
                `مدت: ${transcript.duration ?? '—'} ثانیه`,
              ),
              h(
                'span',
                { class: 'chip' },
                h('span', { class: 'dot' }),
                `زبان: ${transcript.language || '—'}`,
              ),
              transcript.simulated
                ? h(
                    'span',
                    { class: 'chip warn' },
                    h('span', { class: 'dot' }),
                    'موتور داخلی — برای faster-whisper نصب کامل را نصب کنید',
                  )
                : null,
            ),
          ),
        );
      }
      if (pdfResult?.success) {
        children.push(
          h(
            'div',
            { class: 'notice ok', html: ic('check') },
            `PDF ساخته شد: ${pdfResult.file_path} (${fmtBytes(pdfResult.bytes ?? 0)})`,
          ),
        );
      }
    }
    stage.replaceChildren(...children);
  }

  async function transcribe() {
    renderStage({ busy: 'stt' });
    try {
      const res = await api.sttTranscribe(file.path);
      if (res?.success === false) {
        transcript = null;
        renderStage({ error: res.error || 'رونویسی ناموفق بود' });
        return;
      }
      transcript = res;
      pdfResult = null;
      renderStage();
    } catch (e) {
      transcript = null;
      renderStage({ error: msg(e) });
    }
  }

  async function exportPdf() {
    renderStage({ busy: 'pdf' });
    try {
      const report = {
        title: 'رونویسی فایل صوتی',
        subtitle: file.name,
        sections: [
          {
            heading: 'متن رونویسی',
            paragraphs: [transcript.text],
            kpis: [
              { label: 'مدت (ثانیه)', value: String(transcript.duration ?? '—') },
              { label: 'موتور', value: transcript.engine || '—' },
              { label: 'زبان', value: transcript.language || '—' },
            ],
          },
        ],
      };
      pdfResult = await api.pdfExport(report, pdfSiblingPath(file.path));
      renderStage();
      ctx.openEvidence({
        title: 'گزارش رونویسی صوتی',
        steps: [
          { name: 'فایل صوتی', detail: file.name, meta: fmtBytes(file.size) },
          {
            name: 'stt.transcribe',
            detail: `${transcript.engine || '—'} · ${transcript.duration ?? '—'}s`,
            meta: 'هسته پایتون',
          },
          {
            name: 'pdf.export_report',
            detail: pdfResult.file_path,
            meta: fmtBytes(pdfResult.bytes ?? 0),
          },
        ],
      });
    } catch (e) {
      pdfResult = null;
      renderStage({ error: msg(e) });
    }
  }

  async function choose() {
    try {
      const entry = await pickFile('انتخاب فایل صوتی');
      if (entry) {
        file = entry;
        transcript = null;
        pdfResult = null;
        renderStage();
      }
    } catch (e) {
      renderStage({ error: msg(e) });
    }
  }

  const drop = h(
    'div',
    {
      class: 'voice-dropzone',
      ondragover: (e) => {
        e.preventDefault();
        drop.classList.add('over');
      },
      ondragleave: () => drop.classList.remove('over'),
      ondrop: (e) => {
        e.preventDefault();
        drop.classList.remove('over');
        // Browser drops carry no real path — the native dialog is the honest path.
        renderStage({
          error:
            'برای مسیر واقعی، از دکمه «انتخاب فایل» استفاده کنید — کشیدن‌ورها کردن فقط داخل اپ دسکتاپ پشتیبانی می‌شود.',
        });
      },
    },
    stage,
  );

  root.append(
    h(
      'div',
      { class: 'voice-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        h(
          'button',
          { class: 'btn', onclick: choose },
          h('span', { html: ic('upload') }),
          'انتخاب فایل',
        ),
      ),
      drop,
    ),
  );

  renderStage();
}
