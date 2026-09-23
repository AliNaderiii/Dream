/**
 * Voice tool — both directions of real speech:
 *  - «گفتار به متن»: audio file → stt.transcribe (faster-whisper) → Persian PDF
 *  - «متن به گفتار»: text → tts.synthesize (نورال آنلاین edge | آفلاین Piper)
 * Every engine badge is honest: real engines or a clear "unavailable" state —
 * never a fake transcript, never a simulated voice.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFile, pdfSiblingPath, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));
const ENGINE_LABELS = {
  auto: 'خودکار — بهترین موتور موجود',
  edge: 'نورال آنلاین',
  piper: 'آفلاین محلی',
};

export function voiceView(root, ctx) {
  let mode = 'stt'; // 'stt' | 'tts'

  // ---- speech-to-text (existing, unchanged behavior) -----------------------
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

  // ---- text-to-speech (new) ------------------------------------------------
  let engines = []; // tts.engines result rows
  let voices = []; // tts.voices result rows
  let enginesLoaded = false;
  let enginesError = null;
  let ttsResult = null;
  let ttsBusy = false;
  let ttsError = null;

  const ttsText = h('textarea', {
    class: 'input tts-text',
    rows: 4,
    placeholder: 'متنی که باید گفته شود… (فارسی یا انگلیسی)',
    maxlength: '3000',
    oninput: () => renderTtsMeta(),
  });
  const speedInput = h('input', {
    class: 'tts-speed',
    type: 'range',
    min: '0.5',
    max: '1.5',
    step: '0.05',
  });
  const speedVal = h('span', { class: 'mono tts-speed-val', text: '1.00×' });
  const charCount = h('span', { class: 'tts-count mono', text: '۰ / ۳۰۰۰' });

  function currentTts() {
    const saved = ctx.settings.get().tts || {};
    return { engine: saved.engine || 'auto', voice: saved.voice || '', speed: saved.speed || 1 };
  }

  function persistTts(patch) {
    ctx.settings.set({ tts: { ...currentTts(), ...patch } });
  }

  function renderTtsMeta() {
    const len = ttsText.value.length;
    charCount.textContent = `${len} / 3000`;
    const speed = Number(speedInput.value);
    speedVal.textContent = `${speed.toFixed(2)}×`;
  }

  async function loadEngines() {
    try {
      const res = await api.ttsEngines();
      engines = res?.engines || [];
      const vres = await api.ttsVoices();
      voices = vres?.voices || [];
      enginesError = null;
      enginesLoaded = true;
    } catch (e) {
      engines = [];
      voices = [];
      enginesError = msg(e);
    }
    renderTts();
  }

  function engineAvailable(id) {
    const row = engines.find((e) => e.id === id);
    return row ? row.available : false;
  }

  function engineChipFor(id) {
    const row = engines.find((e) => e.id === id);
    if (!row) return null;
    return h(
      'span',
      { class: `chip ${row.available ? 'ok' : 'warn'}` },
      h('span', { class: 'dot' }),
      row.available ? (row.kind === 'online' ? 'آماده — آنلاین' : 'آماده — آفلاین') : 'نصب نیست',
    );
  }

  function renderTts() {
    const t = currentTts();
    const children = [];
    if (enginesError) {
      children.push(
        notice(`${enginesError} — موتورهای صحبت فقط داخل اپلیکیشن دسکتاپ در دسترس‌اند.`),
      );
    } else if (!enginesLoaded) {
      children.push(h('div', { class: 'muted', text: 'در حال بررسی موتورهای صحبت…' }));
    } else {
      const options = [
        {
          id: 'auto',
          label: ENGINE_LABELS.auto,
          available: engineAvailable('edge') || engineAvailable('piper'),
        },
        { id: 'edge', label: 'نورال آنلاین (مایکروسافت)', available: engineAvailable('edge') },
        { id: 'piper', label: 'آفلاین محلی (Piper)', available: engineAvailable('piper') },
      ];
      children.push(
        h(
          'div',
          { class: 'tts-engines' },
          ...options.map((o) =>
            h(
              'button',
              {
                class: `voice-tab tts-engine${t.engine === o.id ? ' active' : ''}`,
                disabled: !o.available,
                title: o.available ? '' : 'این موتور نصب نیست',
                onclick: () => {
                  persistTts({ engine: o.id, voice: '' });
                  renderTts();
                },
              },
              h('span', { text: o.label }),
              engineChipFor(o.id),
            ),
          ),
        ),
      );

      // Voice chips — only meaningful once a concrete engine is chosen.
      if (t.engine === 'auto') {
        children.push(
          h('div', {
            class: 'muted tts-voice-note',
            text: 'حالت خودکار: صدای پیش‌فرض بهترین موتورِ موجود استفاده می‌شود.',
          }),
        );
      } else {
        const list = voices.filter((v) => v.engine === t.engine);
        children.push(
          h(
            'div',
            { class: 'tts-voices' },
            ...list.map((v) =>
              h(
                'button',
                {
                  class: `voice-tab tts-voice${t.voice === v.id ? ' active' : ''}`,
                  disabled: !v.available,
                  title:
                    v.downloaded === false
                      ? 'مدل صدا هنوز دانلود نشده — با اولین استفاده دانلود می‌شود'
                      : '',
                  onclick: () => {
                    persistTts({ voice: v.id });
                    renderTts();
                  },
                },
                h('span', { text: v.label }),
                v.downloaded === false
                  ? h('span', { class: 'chip warn' }, h('span', { class: 'dot' }), 'دانلود نشده')
                  : null,
              ),
            ),
          ),
        );
      }

      children.push(
        h(
          'div',
          { class: 'tts-controls' },
          h(
            'label',
            { class: 'tts-speed-row' },
            h('span', { class: 'field-label', text: 'سرعت' }),
            speedInput,
            speedVal,
          ),
          charCount,
        ),
        ttsText,
        h(
          'div',
          { class: 'voice-actions' },
          h(
            'button',
            {
              class: 'btn btn-primary',
              disabled: ttsBusy || !ttsText.value.trim(),
              onclick: synthesize,
            },
            h('span', { html: ic('speaker') }),
            ttsBusy ? 'در حال ساخت…' : 'ساختن صدا',
          ),
        ),
      );
    }

    if (ttsError) children.push(notice(ttsError));
    if (ttsResult?.success) {
      children.push(
        h(
          'div',
          { class: 'result-panel card tts-result' },
          h('span', { class: 'micro', text: 'SPEECH' }),
          ttsResult.audio_b64
            ? h('audio', {
                controls: true,
                src: `data:${ttsResult.mime};base64,${ttsResult.audio_b64}`,
              })
            : notice(
                `فایل صوتی برای پخش درون‌برنامه‌ای بزرگ است — از مسیر پخش کنید: ${ttsResult.audio_path}`,
                'warn',
              ),
          h(
            'div',
            { class: 'result-meta' },
            h(
              'span',
              { class: 'chip ok' },
              h('span', { class: 'dot' }),
              ttsResult.engine_kind === 'online' ? 'نورال آنلاین' : 'آفلاین محلی',
            ),
            h(
              'span',
              { class: 'chip' },
              h('span', { class: 'dot' }),
              `صدا: ${ttsResult.voice_label}`,
            ),
            h(
              'span',
              { class: 'chip' },
              h('span', { class: 'dot' }),
              `تأخیر: ${ttsResult.latency_ms}ms`,
            ),
            ttsResult.duration
              ? h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `مدت: ${ttsResult.duration}s`,
                )
              : null,
            h('span', { class: 'chip' }, h('span', { class: 'dot' }), fmtBytes(ttsResult.bytes)),
          ),
        ),
      );
    }
    ttsStage.replaceChildren(...children);
    renderTtsMeta();
  }

  async function synthesize() {
    const text = ttsText.value.trim();
    if (!text || ttsBusy) return;
    ttsBusy = true;
    ttsResult = null;
    ttsError = null;
    renderTts();
    try {
      const t = currentTts();
      const res = await api.ttsSynthesize(text, {
        engine: t.engine,
        voice: t.voice,
        speed: Number(speedInput.value) || t.speed,
      });
      if (res?.success === false) {
        ttsError = res.error || 'ساخت صدا ناموفق بود';
      } else {
        ttsResult = res;
        ctx.openEvidence({
          title: 'گفتار ساخته‌شده',
          steps: [
            {
              name: 'متن ورودی',
              detail: `${res.chars} نویسه (پاک‌سازی‌شده)`,
              meta: 'tts.synthesize',
            },
            {
              name: res.engine_kind === 'online' ? 'موتور نورال آنلاین' : 'موتور آفلاین Piper',
              detail: res.voice_label,
              meta: `${res.latency_ms}ms`,
            },
            { name: 'فایل صوتی', detail: res.audio_path, meta: fmtBytes(res.bytes) },
          ],
        });
      }
    } catch (e) {
      ttsError = msg(e);
    } finally {
      ttsBusy = false;
      renderTts();
    }
  }

  const ttsStage = h('div', { class: 'voice-stage' });

  // ---- layout: direction tabs + panes --------------------------------------
  const sttTab = h(
    'button',
    { class: 'voice-tab active', onclick: () => switchMode('stt') },
    h('span', { html: ic('mic') }),
    'گفتار به متن',
  );
  const ttsTab = h(
    'button',
    { class: 'voice-tab', onclick: () => switchMode('tts') },
    h('span', { html: ic('speaker') }),
    'متن به گفتار',
  );
  const tabs = h('div', { class: 'voice-tabs' }, sttTab, ttsTab);

  function switchMode(next) {
    mode = next;
    sttTab.classList.toggle('active', mode === 'stt');
    ttsTab.classList.toggle('active', mode === 'tts');
    sttWrap.classList.toggle('hidden', mode !== 'stt');
    ttsWrap.classList.toggle('hidden', mode !== 'tts');
    if (mode === 'tts' && !enginesLoaded && !enginesError) loadEngines();
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

  const sttWrap = h(
    'div',
    { class: 'voice-pane' },
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
  );
  const ttsWrap = h('div', { class: 'voice-pane hidden' }, ttsStage);

  root.append(h('div', { class: 'voice-view' }, tabs, sttWrap, ttsWrap));

  renderStage();
  renderTts();
}
