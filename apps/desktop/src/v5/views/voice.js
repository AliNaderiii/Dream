/**
 * Voice tool — audio file → real transcription → Persian PDF.
 * The engine badge is always honest: faster-whisper (real) or a clear
 * "unavailable" state — never a fake transcript.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

let file = null;

export function voiceView(root, ctx) {
  const stage = h('div', { class: 'voice-stage' });

  function renderStage() {
    if (!file) {
      stage.replaceChildren(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('mic') }),
          h('span', { class: 'empty-title', text: 'فایل صوتی را اینجا رها کنید' }),
          h('span', { class: 'empty-note', text: 'OGG/Opus (ویس تلگرام)، WAV، MP3 یا M4A — حداکثر ۲۵ مگابایت' }),
          h('span', { class: 'chip voice-engine-chip' }, h('span', { class: 'dot' }), 'موتور رونویسی: نامشخص (پیش‌نمایش)'),
        ),
      );
      return;
    }
    stage.replaceChildren(
      h(
        'div',
        { class: 'voice-file card' },
        h('span', { class: 'voice-file-ic', html: ic('wave') }),
        h('div', { class: 'voice-file-main' },
          h('span', { class: 'voice-file-name', text: file.name }),
          h('span', { class: 'voice-file-meta mono', text: fmtBytes(file.size) }),
        ),
      ),
      h(
        'div',
        { class: 'voice-actions' },
        h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — stt.transcribe' }, h('span', { html: ic('wave') }), 'رونویسی'),
        h('button', { class: 'btn', disabled: true, title: 'فاز ۲ — pdf.export_report' }, h('span', { html: ic('file') }), 'گزارش PDF فارسی'),
      ),
      h('div', { class: 'notice', html: ic('alert') },
        'در نصاب کامل، faster-whisper و مدل base داخل اپ قرار دارند و رونویسی کاملاً آفلاین انجام می‌شود؛ در غیر این صورت وضعیت موتور صادقانه اعلام می‌شود.'),
    );
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
        const f = e.dataTransfer?.files?.[0];
        if (f && f.type.startsWith('audio/') || /\.(ogg|oga|wav|mp3|m4a|opus)$/i.test(f?.name ?? '')) {
          file = f;
          renderStage();
        }
      },
    },
    stage,
  );

  const fileInput = h('input', {
    type: 'file',
    accept: 'audio/*,.ogg,.oga,.opus',
    style: 'display:none',
    onchange: (e) => {
      const f = e.target.files?.[0];
      if (f) {
        file = f;
        renderStage();
      }
    },
  });

  root.append(
    h(
      'div',
      { class: 'voice-view' },
      h('div', { class: 'voice-toolbar' },
        h('button', { class: 'btn', onclick: () => fileInput.click() }, h('span', { html: ic('upload') }), 'انتخاب فایل'),
        fileInput,
      ),
      drop,
    ),
  );

  renderStage();
}
