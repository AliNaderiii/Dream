/**
 * Chat — the center of the workbench. A REAL conversation with the model
 * (BYOK: Ollama / OpenAI-compatible, direct from the app), with every turn
 * recorded into the agent's episodic memory (when the core is available)
 * and every reply carrying its evidence chain (model, latency, memory).
 * No simulated replies, ever.
 */

import { h, fmtTime } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { chatComplete, ModelError } from '../lib/model.js';
import { api, isTauri } from '../lib/bridge.js';

const SESSION_ID = `chat-${Date.now().toString(36)}`;
const messages = []; // {role, text, ts, evidence?}

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

const SYSTEM_PROMPT =
  'تو «دریم» هستی، ایجنت شخصی کاربر که روی سیستم خودش اجرا می‌شود. ' +
  'فارسی روان و دقیق جواب بده و از اظهار نظر بی‌پشتوانه بپرهیز.';

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
  const meta = h(
    'div',
    { class: 'msg-meta' },
    h(
      'span',
      { class: 'msg-author' },
      h('span', { class: 'msg-author-ic', html: ic(isUser ? 'user' : 'bot') }),
      isUser ? 'شما' : 'Dream',
    ),
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
  return h(
    'div',
    { class: `msg ${isUser ? 'from-user' : 'from-agent'} msg-in` },
    meta,
    h(
      'div',
      { class: `msg-bubble ${isUser ? 'user' : 'agent'}` },
      h('div', { class: 'msg-text', text: msg.text }),
    ),
  );
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
  const sendBtn = h(
    'button',
    { class: 'btn btn-primary composer-send', onclick: submit },
    h('span', { html: ic('send') }),
    'ارسال',
  );
  let busy = false;

  function push(msg) {
    messages.push(msg);
    list.append(messageEl(msg, ctx.openEvidence));
    list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' });
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
              h(
                'button',
                {
                  class: 'btn btn-sm',
                  onclick: () => {
                    composer.value = s;
                    composer.focus();
                  },
                },
                s,
              ),
            ),
          ),
        ),
      );
    } else {
      for (const msg of messages) list.append(messageEl(msg, ctx.openEvidence));
      list.scrollTop = list.scrollHeight;
    }
  }

  function typingBubble() {
    return h(
      'div',
      { class: 'msg from-agent msg-in' },
      h(
        'div',
        { class: 'msg-meta' },
        h(
          'span',
          { class: 'msg-author' },
          h('span', { class: 'msg-author-ic', html: ic('bot') }),
          'Dream',
        ),
        h('span', { class: 'msg-time mono', text: '…در حال نوشتن' }),
      ),
      h(
        'div',
        { class: 'msg-bubble agent typing' },
        h('span', { class: 'typing-dot' }),
        h('span', { class: 'typing-dot' }),
        h('span', { class: 'typing-dot' }),
      ),
    );
  }

  /** Best-effort memory recording — the chat itself never depends on it. */
  function remember(role, text) {
    if (!isTauri) return;
    api.episodicRecord(SESSION_ID, role, text).catch(() => {});
  }

  async function submit() {
    const text = composer.value.trim();
    if (!text || busy) return;
    composer.value = '';
    composer.style.height = 'auto';
    busy = true;
    sendBtn.disabled = true;
    push({ role: 'user', text, ts: Date.now() });
    remember('user', text);

    const typing = typingBubble();
    list.append(typing);
    list.scrollTo({ top: list.scrollHeight, behavior: 'smooth' });

    const model = ctx.settings.get().model;
    try {
      const history = [
        { role: 'system', content: SYSTEM_PROMPT },
        ...messages.slice(-12).map((m) => ({ role: m.role, content: m.text })),
      ];
      const reply = await chatComplete(model, history);
      typing.remove();
      push({
        role: 'assistant',
        text: reply.text,
        ts: Date.now(),
        evidence: {
          title: 'پاسخ ایجنت',
          steps: [
            { name: 'مدل', detail: reply.engine, meta: 'اتصال مستقیم BYOK' },
            {
              name: 'حافظه اپیزودیک',
              detail: isTauri ? 'turn در خط زمانی ثبت شد' : 'هسته در دسترس نیست — ثبت نشد',
              meta: 'episodic.record_event',
            },
            { name: 'پاسخ', detail: `${reply.text.length} نویسه`, meta: `${reply.latencyMs}ms` },
          ],
        },
      });
      remember('agent', reply.text);
    } catch (e) {
      typing.remove();
      const hint = e instanceof ModelError ? e.message : e?.message || String(e);
      push({ role: 'system', text: hint, ts: Date.now() });
    } finally {
      busy = false;
      sendBtn.disabled = false;
      composer.focus();
    }
  }

  const toolsMenu = h(
    'div',
    { class: 'tools-menu card' },
    h('span', { class: 'micro', text: 'TOOLS' }),
    ...TOOLS.map((t) =>
      h(
        'button',
        {
          class: 'tools-menu-item',
          onclick: () => {
            toolsMenu.classList.add('hidden');
            location.hash = `#/${t.id}`;
          },
        },
        h('span', { class: 'tools-menu-ic', html: ic(t.icon) }),
        h('span', { text: t.label }),
      ),
    ),
  );
  const attachBtn = h('button', {
    class: 'btn btn-ghost composer-attach',
    title: 'ابزارهای ایجنت',
    html: ic('plus'),
    onclick: (e) => {
      e.stopPropagation();
      toolsMenu.classList.toggle('hidden');
    },
  });
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
        h('div', { class: 'composer-row' }, attachBtn, composer, sendBtn),
        h('div', {
          class: 'composer-hint faint',
          text: 'هیچ پاسخی شبیه‌سازی نمی‌شود — هر خروجی یا واقعی است یا خطایش صادقانه اعلام می‌شود.',
        }),
      ),
    ),
  );

  renderAll();
}
