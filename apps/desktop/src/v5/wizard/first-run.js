/**
 * First-run wizard — four honest steps: welcome, model, core check, done.
 * Everything here is real: the core check pings the actual bridge (and says
 * "browser preview" when there is none), and skipping sets "no model"
 * explicitly rather than pretending a connection exists.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { settings } from '../lib/store.js';
import { status as bridgeStatus } from '../lib/bridge.js';

export function mountWizard(root) {
  let step = 0;
  const model = { provider: 'none', baseUrl: 'http://localhost:11434', apiKey: '', model: '' };

  const overlay = h('div', { class: 'wizard' });
  const progress = h(
    'div',
    { class: 'wizard-progress' },
    ...[0, 1, 2, 3].map((i) =>
      h('span', { class: 'wizard-progress-seg', dataset: { i: String(i) } }),
    ),
  );
  const body = h('div', { class: 'wizard-body' });

  const steps = [
    {
      title: 'به میزکار دریم خوش آمدید',
      render: () => [
        h('span', { class: 'wizard-mark', html: ic('logo') }),
        h('h2', { class: 'wizard-title', text: 'به میزکار دریم خوش آمدید' }),
        h('p', {
          class: 'wizard-lead',
          text: 'یک ایجنت همه‌کاره که روی سیستم شما اجرا می‌شود: یاد می‌سپارد، پژوهش می‌کند، وب را می‌گردد، کد اجرا می‌کند و سند و داده و صدا را به گزارش فارسی تبدیل می‌کند.',
        }),
        h(
          'ul',
          { class: 'wizard-points' },
          point('db', 'حافظه پایدار — خط زمانی و دانسته‌ها، همه روی سیستم شما'),
          point('search', 'پژوهش عمیق — برنامه، منابع واقعی و تأیید صریح شما'),
          point('wave', 'ابزارها — سند، داده، صدا و بات تلگرام با خروجی PDF فارسی'),
        ),
      ],
    },
    {
      title: 'اتصال مدل',
      render: () => [
        h('h2', { class: 'wizard-title', text: 'ایجنت به یک مدل زبانی نیاز دارد' }),
        h('p', {
          class: 'wizard-lead',
          text: 'اگر الان وقت ندارید، «بدون مدل» را انتخاب کنید — بقیه ابزارها مستقل از مدل کار می‌کنند.',
        }),
        h(
          'div',
          { class: 'wizard-providers' },
          providerCard('none', 'بدون مدل', 'بعداً از تنظیمات وصل می‌کنم'),
          providerCard('ollama', 'Ollama محلی', 'رایگان و آفلاین — ollama serve'),
          providerCard('openai', 'API سازگار با OpenAI', 'کلید و آدرس سرور'),
        ),
        model.provider === 'none'
          ? null
          : h(
              'div',
              { class: 'wizard-fields' },
              h(
                'label',
                { class: 'field' },
                h('span', { class: 'field-label', text: 'آدرس سرور' }),
                h('input', {
                  class: 'input',
                  dir: 'ltr',
                  value: model.baseUrl,
                  oninput: (e) => (model.baseUrl = e.target.value),
                }),
              ),
              model.provider === 'openai'
                ? h(
                    'label',
                    { class: 'field' },
                    h('span', { class: 'field-label', text: 'کلید API' }),
                    h('input', {
                      class: 'input',
                      dir: 'ltr',
                      type: 'password',
                      oninput: (e) => (model.apiKey = e.target.value),
                    }),
                  )
                : null,
              h(
                'label',
                { class: 'field' },
                h('span', { class: 'field-label', text: 'نام مدل' }),
                h('input', {
                  class: 'input',
                  dir: 'ltr',
                  placeholder: 'qwen2.5:7b',
                  oninput: (e) => (model.model = e.target.value),
                }),
              ),
            ),
      ],
    },
    {
      title: 'بررسی اجزا',
      render: () => {
        const host = h(
          'div',
          { class: 'wizard-check' },
          h('h2', { class: 'wizard-title', text: 'بررسی اجزای هسته' }),
          h('p', { class: 'wizard-lead', text: 'وضعیت واقعی اجزا، همان‌طور که هست:' }),
        );
        bridgeStatus().then((state) => {
          const rows = [
            [
              'هسته پایتون',
              state === 'ready' ? 'ok' : state === 'browser' ? 'warn' : 'err',
              state === 'ready'
                ? 'متصل'
                : state === 'browser'
                  ? 'پیش‌نمایش مرورگر — داخل اپ دسکتاپ'
                  : 'در دسترس نیست',
            ],
            [
              'OCR فارسی',
              state === 'ready' ? 'ok' : 'unknown',
              state === 'ready' ? 'آماده' : 'پس از اتصال بررسی می‌شود',
            ],
            [
              'PDF فارسی',
              state === 'ready' ? 'ok' : 'unknown',
              state === 'ready' ? 'آماده' : 'پس از اتصال بررسی می‌شود',
            ],
            [
              'رونویسی صدا',
              'unknown',
              state === 'ready' ? 'پس از اولین استفاده مشخص می‌شود' : 'پس از اتصال بررسی می‌شود',
            ],
          ];
          host.append(
            h(
              'div',
              { class: 'wizard-check-rows' },
              ...rows.map(([name, cls, note]) =>
                h(
                  'div',
                  { class: 'wizard-check-row' },
                  h('span', { class: 'wizard-check-name', text: name }),
                  h(
                    'span',
                    {
                      class: `chip ${cls === 'ok' ? 'ok' : cls === 'err' ? 'err' : cls === 'warn' ? 'warn' : ''}`,
                    },
                    h('span', { class: 'dot' }),
                    note,
                  ),
                ),
              ),
            ),
          );
        });
        return [host];
      },
    },
    {
      title: 'آماده‌اید',
      render: () => [
        h('span', { class: 'wizard-mark ok', html: ic('check') }),
        h('h2', { class: 'wizard-title', text: 'همه‌چیز آماده است' }),
        h('p', {
          class: 'wizard-lead',
          text: 'از گفتگو شروع کنید؛ یا یکی از ابزارهای سند، داده و صدا را باز کنید. هر خروجی، زنجیره شواهدش را همراهش دارد.',
        }),
      ],
    },
  ];

  function point(icon, text) {
    return h(
      'li',
      { class: 'wizard-point' },
      h('span', { class: 'wizard-point-ic', html: ic(icon) }),
      text,
    );
  }

  function providerCard(id, title, note) {
    return h(
      'button',
      {
        class: `provider-card card${model.provider === id ? ' active' : ''}`,
        dataset: { provider: id },
        onclick: (e) => {
          model.provider = id;
          for (const el of overlay.querySelectorAll('.provider-card')) {
            el.classList.toggle('active', el === e.currentTarget);
          }
          rerender();
        },
      },
      h('span', { class: 'provider-title', text: title }),
      h('span', { class: 'provider-note', text: note }),
    );
  }

  function rerender() {
    for (const seg of progress.querySelectorAll('.wizard-progress-seg')) {
      seg.classList.toggle('done', Number(seg.dataset.i) <= step);
    }
    body.replaceChildren(...steps[step].render());
    actions.replaceChildren(
      step > 0
        ? h(
            'button',
            {
              class: 'btn',
              onclick: () => {
                step -= 1;
                rerender();
              },
            },
            'قبلی',
          )
        : h('span'),
      h(
        'div',
        { class: 'wizard-actions-end' },
        step < steps.length - 1
          ? h(
              'button',
              {
                class: 'btn btn-primary',
                onclick: () => {
                  step += 1;
                  rerender();
                },
              },
              'بعدی',
            )
          : h(
              'button',
              {
                class: 'btn btn-primary',
                onclick: () => {
                  settings.set({ onboarded: true, model: { ...model } });
                  overlay.remove();
                },
              },
              h('span', { html: ic('check') }),
              'شروع',
            ),
      ),
    );
  }

  const actions = h('div', { class: 'wizard-actions' });

  overlay.append(h('div', { class: 'wizard-card card' }, progress, body, actions));
  root.append(overlay);
  rerender();
}
