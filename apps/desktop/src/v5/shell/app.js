/**
 * App shell: grouped sidebar (agent / memory / tools / channels), topbar,
 * view container, evidence drawer. Dream is a general-purpose agent — the
 * nav says so: chat and research up top, memory its own section, the three
 * document tools are *tools*, and Telegram is one channel of many.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { app, settings } from '../lib/store.js';
import { invoke } from '@tauri-apps/api/core';

import { status as bridgeStatus, isTauri } from '../lib/bridge.js';

import { chatView } from '../views/chat.js';
import { researchView } from '../views/research.js';
import { memoryView } from '../views/memory.js';
import { documentView } from '../views/document.js';
import { dataView } from '../views/data.js';
import { voiceView } from '../views/voice.js';
import { telegramView } from '../views/telegram.js';
import { settingsView } from '../views/settings.js';
import { evidenceDrawer } from './evidence.js';

const VIEWS = {
  chat: {
    title: 'گفتگو',
    subtitle: 'یک مکالمه با ایجنت — همه ابزارها در دسترس',
    icon: 'chat',
    render: chatView,
  },
  research: {
    title: 'پژوهش',
    subtitle: 'پرسش عمیق → برنامه → منابع → گزارش',
    icon: 'search',
    render: researchView,
  },
  memory: {
    title: 'حافظه',
    subtitle: 'رویدادها، دانسته‌ها و خط زمانی ایجنت',
    icon: 'db',
    render: memoryView,
  },
  doc: {
    title: 'سند',
    subtitle: 'عکس و PDF → متن فارسی → گزارش',
    icon: 'doc',
    render: documentView,
  },
  data: {
    title: 'داده',
    subtitle: 'مجموعه‌داده → پرسش → پاسخ با شواهد',
    icon: 'chart',
    render: dataView,
  },
  voice: {
    title: 'صدا',
    subtitle: 'فایل صوتی → رونویسی واقعی → گزارش',
    icon: 'wave',
    render: voiceView,
  },
  telegram: {
    title: 'تلگرام',
    subtitle: 'بات گزارش — عکس/ویس/متن → PDF فارسی',
    icon: 'send',
    render: telegramView,
  },
  settings: {
    title: 'تنظیمات',
    subtitle: 'مدل، ظاهر و وضعیت اجزا',
    icon: 'settings',
    render: settingsView,
  },
};

const NAV_GROUPS = [
  { micro: 'AGENT', items: ['chat', 'research'] },
  { micro: 'MEMORY', items: ['memory'] },
  { micro: 'TOOLS', items: ['doc', 'data', 'voice'] },
  { micro: 'CHANNELS', items: ['telegram'] },
];

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === 'light' ? 'light' : 'dark';
}

function routeFromHash() {
  const id = location.hash.replace(/^#\//, '') || 'chat';
  return id in VIEWS ? id : 'chat';
}

function navItem(id, current) {
  const view = VIEWS[id];
  return h(
    'button',
    {
      class: `nav-item${id === current ? ' active' : ''}`,
      dataset: { view: id },
      onclick: () => {
        location.hash = `#/${id}`;
      },
    },
    h('span', { class: 'nav-ic', html: ic(view.icon) }),
    h('span', { class: 'nav-label', text: view.title }),
  );
}

function chipBridge(state) {
  const map = {
    ready: { cls: 'ok', label: 'هسته متصل' },
    down: { cls: 'err', label: 'هسته قطع' },
    browser: { cls: 'warn', label: 'پیش‌نمایش مرورگر' },
    unknown: { cls: '', label: 'بررسی هسته…' },
  };
  const { cls, label } = map[state] ?? map.unknown;
  return h(
    'span',
    { class: `chip bridge-chip ${cls}`, dataset: { state } },
    h('span', { class: 'dot' }),
    label,
  );
}

/**
 * Native window controls for the frameless window (Windows caption buttons,
 * mirrored to the left corner per RTL convention). The shell exposes the
 * same audited Rust commands the legacy app used.
 */
function winControls() {
  if (!isTauri) return h('span');
  const btn = (title, icon, command, cls = '') =>
    h('button', {
      class: `win-btn ${cls}`,
      title,
      html: ic(icon),
      onclick: () => {
        invoke(command).catch(() => {});
      },
    });
  return h(
    'div',
    { class: 'win-controls' },
    btn('کوچک‌نمایی', 'minus', 'minimize_window'),
    btn('بزرگ‌نمایی', 'square', 'toggle_maximize'),
    btn('بستن', 'x', 'close_window', 'win-close'),
  );
}

function chipModel(model) {
  if (!model || model.provider === 'none' || !model.model) {
    return h('span', { class: 'chip model-chip' }, h('span', { class: 'dot' }), 'بدون مدل');
  }
  const label = `${model.provider === 'ollama' ? 'Ollama' : 'API'} · ${model.model}`;
  return h('span', { class: 'chip model-chip ok' }, h('span', { class: 'dot' }), label);
}

export function mountApp(root) {
  applyTheme(settings.get().theme);
  app.set({ view: routeFromHash() });

  const nav = h(
    'nav',
    { class: 'nav' },
    ...NAV_GROUPS.map((group) =>
      h(
        'div',
        { class: 'nav-group' },
        h('span', { class: 'micro nav-micro', text: group.micro }),
        ...group.items.map((id) => navItem(id, app.get().view)),
      ),
    ),
  );

  const themeBtn = h('button', {
    class: 'btn btn-ghost theme-toggle',
    title: 'تغییر تم',
    onclick: () => {
      const next = settings.get().theme === 'light' ? 'dark' : 'light';
      settings.set({ theme: next });
      applyTheme(next);
    },
  });
  const renderThemeBtn = () => {
    themeBtn.innerHTML = ic(settings.get().theme === 'light' ? 'moon' : 'sun');
    themeBtn.append(settings.get().theme === 'light' ? ' تم تیره' : ' تم روشن');
  };
  renderThemeBtn();
  settings.subscribe(() => renderThemeBtn());

  const bridgeChipHost = h('span', { class: 'chip-host' });
  const modelChipHost = h('span', { class: 'chip-host' });
  const viewTitle = h('h1', { class: 'view-title', text: 'گفتگو' });
  const viewSubtitle = h('span', { class: 'view-subtitle', text: '' });

  const sidebar = h(
    'aside',
    { class: 'sidebar' },
    h(
      'div',
      { class: 'brand' },
      h('span', { class: 'brand-mark', html: ic('logo') }),
      h(
        'span',
        { class: 'brand-text' },
        h('span', { class: 'brand-name', text: 'Dream' }),
        h('span', { class: 'micro', text: 'AGENT WORKBENCH' }),
      ),
    ),
    nav,
    h(
      'div',
      { class: 'sidebar-foot' },
      themeBtn,
      navItem('settings', app.get().view),
      h('span', { class: 'micro version', text: 'v5.0.0-dev' }),
    ),
  );

  // The topbar doubles as the titlebar: draggable via data-tauri-drag-region,
  // with caption buttons at the (RTL-mirrored) left corner.
  const topbar = h(
    'header',
    { class: 'topbar', 'data-tauri-drag-region': true },
    h('div', { class: 'view-heading', 'data-tauri-drag-region': true }, viewTitle, viewSubtitle),
    h('div', { class: 'topbar-chips' }, modelChipHost, bridgeChipHost, winControls()),
  );

  const viewHost = h('main', { id: 'view', class: 'view' });
  const drawer = evidenceDrawer();

  root.append(
    h('div', { class: 'app' }, sidebar, h('div', { class: 'main' }, topbar, viewHost), drawer.el),
  );

  function renderChips() {
    bridgeChipHost.replaceChildren(chipBridge(app.get().bridge));
    modelChipHost.replaceChildren(chipModel(settings.get().model));
  }
  app.subscribe(renderChips);
  settings.subscribe(renderChips);
  renderChips();

  function renderView() {
    const id = routeFromHash();
    app.set({ view: id });
    const view = VIEWS[id];
    viewTitle.textContent = view.title;
    viewSubtitle.textContent = view.subtitle;
    for (const item of nav.querySelectorAll('.nav-item')) {
      item.classList.toggle('active', item.dataset.view === id);
    }
    viewHost.replaceChildren();
    view.render(viewHost, { app, settings, openEvidence: (payload) => drawer.open(payload) });
  }

  window.addEventListener('hashchange', renderView);
  renderView();

  // Poll the real bridge state; in a browser preview it stays honestly "browser".
  const pollBridge = async () => {
    const state = isTauri ? await bridgeStatus() : 'browser';
    if (app.get().bridge !== state) app.set({ bridge: state });
  };
  pollBridge();
  setInterval(pollBridge, 5000);
}
