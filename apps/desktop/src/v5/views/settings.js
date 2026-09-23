/**
 * Settings — model connection (BYOK / local Ollama), appearance, and an
 * honest about panel. Nothing here fakes a working connection.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api } from '../lib/bridge.js';

const PROVIDERS = [
  { id: 'none', title: 'بدون مدل', note: 'اپ کار می‌کند؛ گفتگو غیرفعال می‌ماند.' },
  { id: 'ollama', title: 'Ollama محلی', note: 'کاملاً آفلاین — ollama serve روی همین سیستم.' },
  { id: 'openai', title: 'سازگار با OpenAI', note: 'هر سروری که API سازگار با OpenAI بدهد.' },
];

export function settingsView(root, ctx) {
  const { settings } = ctx;
  const model = { ...settings.get().model };

  const baseUrl = h('input', {
    class: 'input',
    dir: 'ltr',
    placeholder: 'http://localhost:11434',
    value: model.baseUrl || '',
  });
  const apiKey = h('input', {
    class: 'input',
    dir: 'ltr',
    type: 'password',
    placeholder: 'کلید API (اختیاری برای Ollama)',
    value: model.apiKey || '',
  });
  const modelName = h('input', {
    class: 'input',
    dir: 'ltr',
    placeholder: 'مثلاً qwen2.5:7b',
    value: model.model || '',
  });

  const providerCards = h(
    'div',
    { class: 'provider-cards' },
    ...PROVIDERS.map((p) => {
      const card = h(
        'button',
        {
          class: `provider-card card${model.provider === p.id ? ' active' : ''}`,
          dataset: { provider: p.id },
          onclick: () => {
            model.provider = p.id;
            for (const el of providerCards.querySelectorAll('.provider-card')) {
              el.classList.toggle('active', el.dataset.provider === p.id);
            }
            fieldsHost.classList.toggle('hidden', p.id === 'none');
          },
        },
        h('span', { class: 'provider-title', text: p.title }),
        h('span', { class: 'provider-note', text: p.note }),
      );
      return card;
    }),
  );

  const fieldsHost = h(
    'div',
    { class: `model-fields${model.provider === 'none' ? ' hidden' : ''}` },
    field('آدرس سرور', baseUrl),
    field('کلید API', apiKey),
    field('نام مدل', modelName),
  );

  function field(label, input) {
    return h('label', { class: 'field' }, h('span', { class: 'field-label', text: label }), input);
  }

  const saveBtn = h(
    'button',
    {
      class: 'btn btn-primary',
      onclick: () => {
        settings.set({
          model: {
            provider: model.provider,
            baseUrl: baseUrl.value.trim(),
            apiKey: apiKey.value.trim(),
            model: modelName.value.trim(),
          },
        });
        saveNote.textContent = 'ذخیره شد ✓';
        setTimeout(() => (saveNote.textContent = ''), 2000);
      },
    },
    h('span', { html: ic('check') }),
    'ذخیره',
  );
  const saveNote = h('span', { class: 'ok-note', text: '' });

  const themeRow = h(
    'div',
    { class: 'theme-row' },
    ...[
      ['dark', 'تیره'],
      ['light', 'روشن'],
    ].map(([id, label]) => {
      const active = settings.get().theme === id;
      return h(
        'button',
        {
          class: `btn theme-opt${active ? ' active' : ''}`,
          onclick: (e) => {
            settings.set({ theme: id });
            document.documentElement.dataset.theme = id;
            for (const el of themeRow.querySelectorAll('.theme-opt')) {
              el.classList.toggle('active', el === e.currentTarget);
            }
          },
        },
        h('span', { html: ic(id === 'dark' ? 'moon' : 'sun') }),
        label,
      );
    }),
  );

  const bridge = ctx.app.get().bridge;
  const engines = [
    {
      name: 'هسته پایتون (پل)',
      state: bridge === 'ready' ? 'ok' : bridge === 'browser' ? 'warn' : 'err',
      note:
        bridge === 'browser'
          ? 'پیش‌نمایش مرورگر — داخل اپ دسکتاپ'
          : bridge === 'ready'
            ? 'متصل'
            : 'در دسترس نیست',
    },
    { name: 'OCR فارسی', state: 'unknown', note: 'وضعیت در فاز ۲ به‌صورت زنده خوانده می‌شود' },
    {
      name: 'PDF فارسی (HarfBuzz)',
      state: 'unknown',
      note: 'وضعیت در فاز ۲ به‌صورت زنده خوانده می‌شود',
    },
    {
      name: 'رونویسی صدا (faster-whisper)',
      state: 'unknown',
      note: 'در نصاب کامل به‌صورت آفلاین فعال است',
    },
    {
      name: 'صحبت (edge-tts نورال + Piper آفلاین)',
      state: 'unknown',
      note: 'استودیوی صدا → «متن به گفتار» و دکمه «گفتن» در گفتگو',
    },
  ];

  // ---- speech (TTS) --------------------------------------------------------
  const tts = { engine: 'auto', voice: '', speed: 1, ...(settings.get().tts || {}) };
  const ttsEngineSel = h(
    'select',
    { class: 'input' },
    h('option', { value: 'auto', text: 'خودکار — بهترین موتور موجود' }),
    h('option', { value: 'edge', text: 'نورال آنلاین (مایکروسافت edge-tts)' }),
    h('option', { value: 'piper', text: 'آفلاین محلی (Piper)' }),
  );
  ttsEngineSel.value = tts.engine;
  const ttsVoiceSel = h('select', { class: 'input' });
  const ttsVoiceNote = h('span', { class: 'muted tts-voice-note', text: '' });
  const ttsSpeed = h('input', {
    class: 'tts-speed',
    type: 'range',
    min: '0.5',
    max: '1.5',
    step: '0.05',
  });
  ttsSpeed.value = String(tts.speed ?? 1);
  const ttsSpeedVal = h('span', {
    class: 'mono tts-speed-val',
    text: `${Number(tts.speed ?? 1).toFixed(2)}×`,
  });
  const ttsStatus = h('div', { class: 'tts-status' });
  const ttsSaveNote = h('span', { class: 'ok-note', text: '' });

  async function refreshTtsVoices() {
    ttsVoiceSel.replaceChildren();
    if (ttsEngineSel.value === 'auto') {
      ttsVoiceSel.append(h('option', { value: '', text: 'پیش‌فرض موتورِ انتخابی' }));
      ttsVoiceSel.value = '';
      return;
    }
    try {
      const res = await api.ttsVoices(ttsEngineSel.value);
      const list = (res?.voices || []).filter((v) => v.engine === ttsEngineSel.value);
      ttsVoiceSel.append(h('option', { value: '', text: 'پیش‌فرض' }));
      for (const v of list) ttsVoiceSel.append(h('option', { value: v.id, text: v.label }));
      ttsVoiceSel.value = list.some((v) => v.id === tts.voice) ? tts.voice : '';
    } catch (e) {
      ttsVoiceNote.textContent = e?.message || '';
    }
  }

  async function refreshTtsStatus() {
    try {
      const res = await api.ttsEngines();
      const rows = res?.engines || [];
      const edge = rows.find((r) => r.id === 'edge');
      const piper = rows.find((r) => r.id === 'piper');
      const any = edge?.available || piper?.available;
      ttsStatus.replaceChildren(
        h(
          'div',
          { class: 'about-engine' },
          h('span', { class: 'engine-name', text: 'موتورهای صحبت' }),
          h(
            'span',
            { class: `chip ${any ? 'ok' : 'warn'}` },
            h('span', { class: 'dot' }),
            `نورال آنلاین ${edge?.available ? '✓' : '✗'} · آفلاین Piper ${piper?.available ? '✓' : '✗'}`,
          ),
        ),
      );
    } catch {
      ttsStatus.replaceChildren(
        h('div', {
          class: 'muted',
          text: 'پیش‌نمایش مرورگر — موتورها داخل اپ دسکتاپ بررسی می‌شوند',
        }),
      );
    }
    refreshTtsVoices();
  }

  ttsEngineSel.addEventListener('change', refreshTtsVoices);
  ttsSpeed.addEventListener('input', () => {
    ttsSpeedVal.textContent = `${Number(ttsSpeed.value).toFixed(2)}×`;
  });

  const ttsSaveBtn = h(
    'button',
    {
      class: 'btn btn-primary',
      onclick: () => {
        settings.set({
          tts: {
            engine: ttsEngineSel.value,
            voice: ttsVoiceSel.value,
            speed: Number(ttsSpeed.value),
          },
        });
        ttsSaveNote.textContent = 'ذخیره شد ✓';
        setTimeout(() => (ttsSaveNote.textContent = ''), 2000);
      },
    },
    h('span', { html: ic('check') }),
    'ذخیره',
  );

  refreshTtsStatus();

  root.append(
    h(
      'div',
      { class: 'settings-view' },
      section(
        'MODEL',
        'مدل',
        h(
          'div',
          { class: 'section-card card' },
          providerCards,
          fieldsHost,
          h('div', { class: 'settings-actions' }, saveBtn, saveNote),
        ),
      ),

      section(
        'SPEECH',
        'صحبت (متن به گفتار)',
        h(
          'div',
          { class: 'section-card card' },
          field('موتور', ttsEngineSel),
          field('صدا', h('div', { class: 'tts-voice-row' }, ttsVoiceSel, ttsVoiceNote)),
          field('سرعت', h('div', { class: 'tts-speed-row' }, ttsSpeed, ttsSpeedVal)),
          ttsStatus,
          h('div', { class: 'settings-actions' }, ttsSaveBtn, ttsSaveNote),
        ),
      ),

      section('APPEARANCE', 'ظاهر', h('div', { class: 'section-card card theme-card' }, themeRow)),

      section(
        'ABOUT',
        'درباره',
        h(
          'div',
          { class: 'section-card card about-card' },
          h(
            'div',
            { class: 'about-row' },
            h('span', { class: 'muted', text: 'نسخه' }),
            h('span', { class: 'mono', text: '5.2.0' }),
          ),
          h(
            'div',
            { class: 'about-row' },
            h('span', { class: 'muted', text: 'پروتکل پل' }),
            h('span', { class: 'mono', text: 'bridge_send · JSON-RPC' }),
          ),
          h(
            'div',
            { class: 'about-engines' },
            h('span', { class: 'micro', text: 'COMPONENT STATUS' }),
            ...engines.map((eng) =>
              h(
                'div',
                { class: 'about-engine' },
                h('span', { class: 'engine-name', text: eng.name }),
                h(
                  'span',
                  {
                    class: `chip ${eng.state === 'ok' ? 'ok' : eng.state === 'err' ? 'err' : eng.state === 'warn' ? 'warn' : ''}`,
                  },
                  h('span', { class: 'dot' }),
                  eng.note,
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

function section(micro, title, ...children) {
  return h(
    'section',
    { class: 'settings-section' },
    h(
      'div',
      { class: 'settings-section-head' },
      h('span', { class: 'micro', text: micro }),
      h('span', { class: 'settings-section-title', text: title }),
    ),
    ...children,
  );
}
