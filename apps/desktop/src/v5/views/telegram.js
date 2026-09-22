/**
 * Telegram channel — the real report bot (core v4.7): photo → Persian OCR,
 * voice → transcription, text → structured report; every path answers with a
 * Persian PDF in the same chat. One agent, every surface.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

export function telegramView(root, ctx) {
  root.append(
    h(
      'div',
      { class: 'telegram-view' },
      h(
        'div',
        { class: 'section-card card' },
        h('span', { class: 'micro', text: 'BOT TOKEN' }),
        h('input', { class: 'input', dir: 'ltr', type: 'password', placeholder: 'توکن بات از @BotFather' }),
        h('div', { class: 'telegram-actions' },
          h('button', { class: 'btn btn-primary', disabled: true, title: 'فاز ۲ — reportbot.start' },
            h('span', { html: ic('send') }), 'شروع بات'),
          h('button', { class: 'btn', disabled: true, title: 'فاز ۲ — reportbot.stop' },
            h('span', { html: ic('x') }), 'توقف'),
          h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'متوقف')),
        h('div', { class: 'notice', html: ic('alert') },
          'بات در هسته واقعی است (v4.7): عکس → OCR فارسی، صدا → رونویسی، متن → گزارش — پاسخ همیشه PDF فارسی در همان چت. اتصال رابط در فاز ۲.'),
      ),
      h(
        'div',
        { class: 'telegram-flows' },
        ...[
          ['عکس', 'OCR فارسی → فیلدهای فاکتور → PDF'],
          ['ویس', 'رونویسی (faster-whisper در نصاب کامل) → PDF'],
          ['متن', 'گزارش ساختاریافته → PDF'],
        ].map(([t, note]) =>
          h('div', { class: 'telegram-flow card' },
            h('span', { class: 'telegram-flow-title', text: t }),
            h('span', { class: 'telegram-flow-note', text: note })),
        ),
      ),
      h(
        'div',
        { class: 'empty empty-sm' },
        h('span', { html: ic('bot') }),
        h('span', { class: 'empty-title', text: 'رویدادی ثبت نشده' }),
        h('span', { class: 'empty-note', text: 'پس از شروع، آخرین رویدادهای بات اینجا نمایش داده می‌شود.' }),
      ),
    ),
  );
}
