/**
 * Settings — model connection (BYOK / local Ollama), appearance, and an
 * honest about panel. Nothing here fakes a working connection.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

const PROVIDERS = [
  { id: 'none', title: 'بدون مدل', note: 'اپ کار می‌کند؛ گفتگو غیرفعال می‌ماند.' },
  { id: 'ollama', title: 'Ollama محلی', note: 'کاملاً آفلاین — ollama serve روی همین سیستم.' },
  { id: 'openai', title: 'سازگار با OpenAI', note: 'هر سروری که API سازگار با OpenAI بدهد.' },
];

export function settingsView(root, ctx) {
  const { settings } = ctx;
  const model = { ...settings.get().model };

  const baseUrl = h('input', { class: 'input', dir: 'ltr', placeholder: 'http://localhost:11434', value: model.baseUrl || '' });
  const apiKey = h('input', { class: 'input', dir: 'ltr', type: 'password', placeholder: 'کلید API (اختیاری برای Ollama)', value: model.apiKey || '' });
  const modelName = h('input', { class: 'input', dir: 'ltr', placeholder: 'مثلاً qwen2.5:7b', value: model.model || '' });

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
    { name: 'هسته پایتون (پل)', state: bridge === 'ready' ? 'ok' : bridge === 'browser' ? 'warn' : 'err', note: bridge === 'browser' ? 'پیش‌نمایش مرورگر — داخل اپ دسکتاپ' : bridge === 'ready' ? 'متصل' : 'در دسترس نیست' },
    { name: 'OCR فارسی', state: 'unknown', note: 'وضعیت در فاز ۲ به‌صورت زنده خوانده می‌شود' },
    { name: 'PDF فارسی (HarfBuzz)', state: 'unknown', note: 'وضعیت در فاز ۲ به‌صورت زنده خوانده می‌شود' },
    { name: 'رونویسی صدا (faster-whisper)', state: 'unknown', note: 'در نصاب کامل به‌صورت آفلاین فعال است' },
  ];

  root.append(
    h(
      'div',
      { class: 'settings-view' },
      section('MODEL', 'مدل',
        h('div', { class: 'section-card card' },
          providerCards,
          fieldsHost,
          h('div', { class: 'settings-actions' }, saveBtn, saveNote))),

      section('APPEARANCE', 'ظاهر',
        h('div', { class: 'section-card card theme-card' }, themeRow)),

      section('ABOUT', 'درباره',
        h('div', { class: 'section-card card about-card' },
          h('div', { class: 'about-row' }, h('span', { class: 'muted', text: 'نسخه' }), h('span', { class: 'mono', text: '5.0.0-dev' })),
          h('div', { class: 'about-row' }, h('span', { class: 'muted', text: 'پروتکل پل' }), h('span', { class: 'mono', text: 'bridge_send · JSON-RPC' })),
          h('div', { class: 'about-engines' },
            h('span', { class: 'micro', text: 'COMPONENT STATUS' }),
            ...engines.map((eng) =>
              h('div', { class: 'about-engine' },
                h('span', { class: 'engine-name', text: eng.name }),
                h('span', { class: `chip ${eng.state === 'ok' ? 'ok' : eng.state === 'err' ? 'err' : eng.state === 'warn' ? 'warn' : ''}` },
                  h('span', { class: 'dot' }), eng.note)),
            )))),
    ),
  );
}

function section(micro, title, ...children) {
  return h('section', { class: 'settings-section' },
    h('div', { class: 'settings-section-head' },
      h('span', { class: 'micro', text: micro }),
      h('span', { class: 'settings-section-title', text: title })),
    ...children);
}
