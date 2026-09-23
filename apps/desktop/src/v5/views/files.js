/**
 * Files — browse the registered workspace roots and preview files, wired to
 * the real workspace.* bridge methods. Registering a folder is an explicit
 * user action (native dialog); nothing is ever scanned silently.
 */

import { h, fmtBytes } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, pickFolder, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const TYPE_LABELS = {
  directory: 'پوشه',
  text: 'متن',
  image: 'تصویر',
  audio: 'صدا',
  video: 'ویدیو',
  archive: 'آرشیو',
  code: 'کد',
  binary: 'باینری',
};

export function filesView(root) {
  let roots = []; // [{root_id, name, path, ...}]
  let activeRoot = null; // root row
  let relPath = ''; // '' = root itself, 'a/b' = subfolder
  let listing = null; // files_list result
  let preview = null; // files_preview result
  let busy = '';
  let error = null;

  const stage = h('div', { class: 'files-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function breadcrumb() {
    const parts = relPath ? relPath.split('/') : [];
    const crumbs = [
      h('button', { class: 'crumb', onclick: () => go('') }, activeRoot.name || 'ریشه'),
    ];
    let acc = '';
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      const target = acc;
      crumbs.push(h('span', { class: 'crumb-sep', text: '‹' }));
      crumbs.push(h('button', { class: 'crumb', onclick: () => go(target) }, part));
    }
    return h('div', { class: 'files-crumbs' }, ...crumbs);
  }

  function entryRow(entry) {
    return h(
      'button',
      {
        class: 'files-row',
        onclick: () => {
          if (entry.is_dir) go(entry.path);
          else showPreview(entry);
        },
      },
      h('span', { class: 'files-row-ic', html: ic(entry.is_dir ? 'folder' : 'file') }),
      h(
        'div',
        { class: 'files-row-main' },
        h('span', { class: 'files-row-name', text: entry.name }),
        h('span', {
          class: 'files-row-meta mono',
          text: entry.is_dir ? '' : fmtBytes(entry.size ?? 0),
        }),
      ),
      h(
        'span',
        { class: `chip${entry.is_dir ? '' : ' faint-chip'}` },
        h('span', { class: 'dot' }),
        TYPE_LABELS[entry.type] || entry.type || '—',
      ),
    );
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, busy));

    if (!activeRoot) {
      if (!roots.length && !busy && !error) {
        children.push(
          h(
            'div',
            { class: 'voice-drop card' },
            h('span', { class: 'voice-drop-ic', html: ic('folder') }),
            h('span', { class: 'empty-title', text: 'هنوز پوشه‌ای ثبت نشده است' }),
            h('span', {
              class: 'empty-note',
              text: 'یک پوشه از سیستم خود را ثبت کنید تا دریم بتواند فایل‌هایش را ببیند — ثبت کردن با انتخاب صریح شما انجام می‌شود.',
            }),
          ),
        );
      } else if (roots.length) {
        children.push(
          h(
            'div',
            { class: 'files-roots' },
            ...roots.map((r) =>
              h(
                'button',
                {
                  class: 'files-root card',
                  onclick: () => {
                    activeRoot = r;
                    relPath = '';
                    preview = null;
                    go('');
                  },
                },
                h('span', { class: 'files-row-ic', html: ic('folder') }),
                h(
                  'div',
                  { class: 'files-row-main' },
                  h('span', { class: 'files-row-name', text: r.name || r.root_id }),
                  h('span', { class: 'files-row-meta mono', text: r.path }),
                ),
              ),
            ),
          ),
        );
      }
    } else {
      children.push(breadcrumb());
      if (listing?.entries?.length) {
        children.push(h('div', { class: 'files-list card' }, ...listing.entries.map(entryRow)));
        if (listing.has_more) {
          children.push(
            h(
              'div',
              { class: 'voice-actions' },
              h(
                'button',
                {
                  class: 'btn',
                  onclick: () => loadList(listing.next_cursor ?? 0, true),
                },
                h('span', { html: ic('arrow') }),
                'موارد بیشتر',
              ),
            ),
          );
        }
      } else if (!busy) {
        children.push(
          h(
            'div',
            { class: 'empty' },
            h('span', { class: 'empty-title', text: 'این پوشه خالی است' }),
          ),
        );
      }

      if (preview) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'PREVIEW' }),
            h('span', { class: 'files-preview-name mono', text: preview.path }),
            preview.text
              ? h('pre', { class: 'files-preview-text' }, preview.text)
              : h('span', {
                  class: 'empty-note',
                  text: 'پیش‌نمایش متنی برای این فایل وجود ندارد (باینری یا بسیار بزرگ).',
                }),
            preview.truncated
              ? h(
                  'span',
                  { class: 'chip warn' },
                  h('span', { class: 'dot' }),
                  'پیش‌نمایش کوتاه‌شده',
                )
              : null,
          ),
        );
      }
    }
    stage.replaceChildren(...children);
  }

  async function loadRoots() {
    busy = 'در حال خواندن پوشه‌های ثبت‌شده…';
    error = null;
    renderStage();
    try {
      const res = await api.wsRootsList();
      roots = res?.roots ?? [];
    } catch (e) {
      roots = [];
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function loadList(cursor = 0, append = false) {
    busy = 'در حال فهرست‌کردن…';
    error = null;
    renderStage();
    try {
      const res = await api.wsFilesList(activeRoot.root_id, relPath, cursor);
      if (append && listing) {
        listing = { ...res, entries: [...(listing.entries ?? []), ...(res.entries ?? [])] };
      } else {
        listing = res;
      }
    } catch (e) {
      listing = null;
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function go(path) {
    relPath = path;
    preview = null;
    await loadList();
  }

  async function showPreview(entry) {
    busy = `در حال پیش‌نمایش «${entry.name}»…`;
    error = null;
    renderStage();
    try {
      preview = await api.wsFilesPreview(activeRoot.root_id, entry.path);
    } catch (e) {
      preview = null;
      error = msg(e);
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function registerFolder() {
    try {
      const folder = await pickFolder('انتخاب پوشه برای ثبت در دریم');
      if (!folder) return;
      busy = 'در حال ثبت پوشه…';
      renderStage();
      const res = await api.wsRootsRegister(folder);
      if (res?.success === false) {
        error = res.error || 'ثبت پوشه ناموفق بود';
      } else {
        activeRoot = null;
        relPath = '';
        preview = null;
      }
      busy = '';
      await loadRoots();
    } catch (e) {
      busy = '';
      error = msg(e);
      renderStage();
    }
  }

  root.append(
    h(
      'div',
      { class: 'files-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        h(
          'button',
          { class: 'btn btn-primary', onclick: registerFolder },
          h('span', { html: ic('plus') }),
          'افزودن پوشه',
        ),
        activeRoot
          ? h(
              'button',
              {
                class: 'btn',
                onclick: () => {
                  activeRoot = null;
                  relPath = '';
                  preview = null;
                  listing = null;
                  renderStage();
                  loadRoots();
                },
              },
              h('span', { html: ic('arrow') }),
              'همه پوشه‌ها',
            )
          : null,
      ),
      stage,
    ),
  );

  renderStage();
  loadRoots();
}
