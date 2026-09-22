/**
 * Telegram channel — the real report bot (core v4.7), fully wired:
 * reportbot.start / stop / status with live polling.
 * Photo → Persian OCR, voice → transcription, text → report → Persian PDF.
 */

import { h, fmtTime } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

export function telegramView(root) {
  let pollTimer = null;

  const tokenInput = h('input', {
    class: 'input',
    dir: 'ltr',
    type: 'password',
    placeholder: 'توکن بات از @BotFather (مثلاً 123456:ABC-DEF…)',
  });
  const statusHost = h('div', { class: 'telegram-status' });
  const startBtn = h(
    'button',
    {
      class: 'btn btn-primary',
      onclick: start,
    },
    h('span', { html: ic('send') }),
    'شروع بات',
  );
  const stopBtn = h(
    'button',
    { class: 'btn', onclick: stop },
    h('span', { html: ic('x') }),
    'توقف',
  );

  function render(status, error = null) {
    const running = status?.running === true;
    startBtn.disabled = running;
    stopBtn.disabled = !running;
    tokenInput.disabled = running;

    const children = [];
    if (error) {
      children.push(h('div', { class: 'notice err', html: ic('alert') }, error));
    }
    if (status) {
      const engine = status.stt_engine || '—';
      const simulated = /simulat|built/i.test(engine);
      children.push(
        h(
          'div',
          { class: 'telegram-stats' },
          h(
            'span',
            { class: `chip ${running ? 'ok' : ''}` },
            h('span', { class: 'dot' }),
            running ? 'در حال اجرا' : 'متوقف',
          ),
          h(
            'span',
            { class: `chip ${simulated ? 'warn' : running ? 'ok' : ''}` },
            h('span', { class: 'dot' }),
            `موتور صدا: ${engine}`,
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `${status.updates_processed ?? 0} پیام پردازش‌شده`,
          ),
          status.token_fingerprint
            ? h(
                'span',
                { class: 'chip' },
                h('span', { class: 'dot' }),
                `توکن: ${status.token_fingerprint}`,
              )
            : null,
        ),
      );
      if (status.last_error) {
        children.push(
          h(
            'div',
            { class: 'notice warn', html: ic('alert') },
            `آخرین خطای بات: ${status.last_error}`,
          ),
        );
      }
      const events = Array.isArray(status.events) ? status.events.slice(-8).reverse() : [];
      if (events.length) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'RECENT EVENTS' }),
            ...events.map((ev) =>
              h(
                'div',
                { class: 'log-row' },
                h('span', { class: 'log-time mono', text: fmtTime(ev.ts * 1000) }),
                h('span', { class: 'log-kind', text: ev.kind }),
                h('span', {
                  class: 'log-detail muted',
                  text: ev.chat_id ? `چت ${ev.chat_id}` : '—',
                }),
              ),
            ),
          ),
        );
      }
    } else if (!error) {
      children.push(
        h(
          'div',
          { class: 'notice', html: ic('alert') },
          'بات متوقف است. توکن را وارد کنید و «شروع بات» را بزنید — پاسخ‌ها در همان چت تلگرام به‌صورت PDF فارسی ارسال می‌شود.',
        ),
      );
    }
    statusHost.replaceChildren(...children);
  }

  function poll() {
    api
      .reportbotStatus()
      .then((s) => render(s))
      .catch(() => render(null));
  }

  async function start() {
    const token = tokenInput.value.trim();
    if (!token) {
      render(null, 'توکن را وارد کنید — از @BotFather بگیرید.');
      return;
    }
    render({ running: false });
    try {
      await api.reportbotStart(token);
      poll();
    } catch (e) {
      render(null, msg(e));
    }
  }

  async function stop() {
    try {
      await api.reportbotStop();
      poll();
    } catch (e) {
      render(null, msg(e));
    }
  }

  // Live status while the view is mounted.
  poll();
  pollTimer = setInterval(poll, 5000);
  const origRender = root.replaceChildren.bind(root);
  root.replaceChildren = (...args) => {
    clearInterval(pollTimer);
    origRender(...args);
  };

  root.append(
    h(
      'div',
      { class: 'telegram-view' },
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'BOT TOKEN' }),
        tokenInput,
        h('div', { class: 'telegram-actions' }, startBtn, stopBtn),
        statusHost,
      ),
      h(
        'div',
        { class: 'telegram-flows' },
        ...[
          ['عکس', 'OCR فارسی → فیلدهای فاکتور → PDF'],
          ['ویس', 'رونویسی (faster-whisper در نصاب کامل) → PDF'],
          ['متن', 'گزارش ساختاریافته → PDF'],
        ].map(([t, note]) =>
          h(
            'div',
            { class: 'telegram-flow card' },
            h('span', { class: 'telegram-flow-title', text: t }),
            h('span', { class: 'telegram-flow-note', text: note }),
          ),
        ),
      ),
    ),
  );

  render(null);
}
