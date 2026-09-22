/**
 * Chat — the center of the workbench. One conversation with a general-purpose
 * agent: it remembers, researches, browses, runs code, and drives the
 * document/data/voice tools. No simulated replies, ever.
 */

import { h, fmtTime } from '../lib/dom.js';
import { ic } from '../lib/icons.js';

/** Ephemeral, in-memory conversation (persistence arrives with phase 2). */
const messages = [];

const SUGGESTIONS = [
  'یادت باشد: جلسه‌های پروژه را جمعه‌ها مرور کن',
  'پژوهش عمیق درباره بازار پنل خورشیدی انجام بده',
  'این فاکتور را بخوان و جمعش را کنترل کن',
  'از داده فروش، روند ماهانه را استخراج کن',
];

const TOOLS = [
  { id: 'doc', label: 'سند — OCR و PDF', icon: 'doc' },
  { id: 'data', label: 'داده — تحلیل با شواهد', icon: 'chart' },
  { id: 'voice', label: 'صدا — رونویسی', icon: 'wave' },
  { id: 'research', label: 'پژوهش — وب و منابع', icon: 'search' },
  { id: 'memory', label: 'حافظه — خط زمانی', icon: 'db' },
];

function messageEl(msg, openEvidence) {
  if (msg.role === 'system') {
    return h(
      'div',
      { class: 'msg msg-system' },
      h('span', { class: 'notice warn', html: ic('alert') }),
      h('span', { class: 'system-text', text: msg.text }),
    );
  }

  const isUser = msg.role === 'user';
  const bubble = h(
    'div',
    { class: `msg-bubble ${isUser ? 'user' : 'agent'}` },
    h('div', { class: 'msg-text', text: msg.text }),
  );

  const meta = h(
    'div',
    { class: 'msg-meta' },
    h('span', { class: 'msg-author' }, h('span', { class: 'msg-author-ic', html: ic(isUser ? 'user' : 'bot') }), isUser ? 'شما' : 'Dream'),
    h('span', { class: 'msg-time mono', text: fmtTime(msg.ts) }),
    msg.evidence
      ? h(
          'button',
          {
            class: 'btn btn-ghost btn-sm evidence-link',
            onclick: () => openEvidence(msg.evidence),
          },
          h('span', { html: ic('evidence') }),
          `شواهد (${msg.evidence.steps.length})`,
        )
      : null,
  );

  return h('div', { class: `msg ${isUser ? 'from-user' : 'from-agent'}` }, meta, bubble);
}

export function chatView(root, ctx) {
  const list = h('div', { class: 'chat-list' });
  const composer = h('textarea', {
    class: 'composer-input',
    rows: 1,
    placeholder: 'هر کاری داری بگو — یاد بسپار، پژوهش کن، تحلیل کن، رونویسی کن…',
    onkeydown: (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    },
    oninput: (e) => {
      e.target.style.height = 'auto';
      e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
    },
  });

  function push(msg) {
    messages.push(msg);
    list.append(messageEl(msg, ctx.openEvidence));
    list.scrollTop = list.scrollHeight;
  }

  function renderAll() {
    list.replaceChildren();
    if (messages.length === 0) {
      list.append(
        h(
          'div',
          { class: 'chat-empty' },
          h('span', { class: 'chat-empty-mark', html: ic('logo') }),
          h('span', { class: 'chat-empty-title', text: 'ایجنت همه‌کاره شخصی شما' }),
          h(
            'span',
            { class: 'chat-empty-note' },
            'حافظه پایدار، پژوهش عمیق، مرور وب، سندباکس کد و ابزارهای سند و داده و صدا — همه روی سیستم خودتان، با شواهد قابل بازبینی.',
          ),
          h(
            'div',
            { class: 'chat-suggestions' },
            ...SUGGESTIONS.map((s) =>
              h('button', { class: 'btn btn-sm', onclick: () => { composer.value = s; composer.focus(); } }, s),
            ),
          ),
        ),
      );
    } else {
      for (const msg of messages) list.append(messageEl(msg, ctx.openEvidence));
      list.scrollTop = list.scrollHeight;
    }
  }

  function honestSystemReply() {
    const { bridge } = ctx.app.get();
    const model = ctx.settings.get().model;
    if (bridge === 'browser') {
      return 'هسته پایتون فقط داخل اپلیکیشن دسکتاپ در دسترس است — این پیش‌نمایش مرورگر است و پیام ارسال نشد.';
    }
    if (bridge !== 'ready') {
      return 'هسته پایتون در دسترس نیست؛ اتصال را در تنظیمات بررسی کنید. پیام ذخیره شد اما پردازش نشد.';
    }
    if (!model || model.provider === 'none' || !model.model) {
      return 'مدلی متصل نیست. از «تنظیمات → مدل» یک مدل محلی (Ollama) یا API معتبر تنظیم کنید.';
    }
    return 'اتصال گفتگو به هسته در فاز ۲ فعال می‌شود — پیام شما ذخیره شد.';
  }

  function submit() {
    const text = composer.value.trim();
    if (!text) return;
    composer.value = '';
    composer.style.height = 'auto';
    push({ role: 'user', text, ts: Date.now() });
    setTimeout(() => push({ role: 'system', text: honestSystemReply(), ts: Date.now() }), 60);
  }

  // Tools menu — the agent's toolbox, one click away in the composer.
  const toolsMenu = h(
    'div',
    { class: 'tools-menu card' },
    h('span', { class: 'micro', text: 'TOOLS' }),
    ...TOOLS.map((t) =>
      h('button', {
        class: 'tools-menu-item',
        onclick: () => {
          toolsMenu.classList.add('hidden');
          location.hash = `#/${t.id}`;
        },
      },
      h('span', { class: 'tools-menu-ic', html: ic(t.icon) }),
      h('span', { text: t.label }))),
    );
  const attachBtn = h(
    'button',
    {
      class: 'btn btn-ghost composer-attach',
      title: 'ابزارهای ایجنت',
      html: ic('plus'),
      onclick: (e) => {
        e.stopPropagation();
        toolsMenu.classList.toggle('hidden');
      },
    },
  );
  document.addEventListener('click', () => toolsMenu.classList.add('hidden'));

  root.append(
    h(
      'div',
      { class: 'chat-view' },
      list,
      h(
        'div',
        { class: 'composer card' },
        toolsMenu,
        h(
          'div',
          { class: 'composer-row' },
          attachBtn,
          composer,
          h('button', { class: 'btn btn-primary composer-send', onclick: submit }, h('span', { html: ic('send') }), 'ارسال'),
        ),
        h('div', { class: 'composer-hint faint', text: 'هیچ پاسخی شبیه‌سازی نمی‌شود — هر خروجی یا واقعی است یا خطایش صادقانه اعلام می‌شود.' }),
      ),
    ),
  );

  renderAll();
}
