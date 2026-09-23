/**
 * Web — honest, human-in-the-loop web reading on the real browse.* bridge:
 * propose a URL, approve it yourself, and only then the core fetches it
 * (SSRF-guarded, prompt-injection-scanned). Extracted links can be followed
 * the same way. No YOLO, no auto-fetch, no fake pages.
 */

import { h } from '../lib/dom.js';
import { ic } from '../lib/icons.js';
import { api, BridgeUnavailableError } from '../lib/bridge.js';

const msg = (e) => (e instanceof BridgeUnavailableError ? e.message : e?.message || String(e));

const STATUS_FA = {
  APPROVAL_PENDING: { label: 'در انتظار تأیید شما', cls: 'warn' },
  fetched: { label: 'واکشی‌شده', cls: 'ok' },
  refused: { label: 'رد شد (سیستم)', cls: 'err' },
  denied: { label: 'رد شد (شما)', cls: 'err' },
};

export function webView(root, ctx) {
  let drafts = [];
  let selected = null; // fetched draft shown in detail
  let busy = '';
  let error = null;

  const urlInput = h('input', {
    class: 'input web-url',
    dir: 'ltr',
    placeholder: 'https://example.com/page',
  });
  const stage = h('div', { class: 'web-stage' });

  function notice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function statusChip(status) {
    const s = STATUS_FA[status] || { label: status || '—', cls: '' };
    return h('span', { class: `chip ${s.cls}` }, h('span', { class: 'dot' }), s.label);
  }

  function renderStage() {
    const children = [];
    if (error) children.push(notice(error));
    if (busy) children.push(h('div', { class: 'notice', html: ic('refresh') }, busy));

    if (!drafts.length && !busy && !error) {
      children.push(
        h(
          'div',
          { class: 'voice-drop card' },
          h('span', { class: 'voice-drop-ic', html: ic('globe') }),
          h('span', { class: 'empty-title', text: 'نشانی‌ای پیشنهاد نشده است' }),
          h('span', {
            class: 'empty-note',
            text: 'نشانی را وارد و «پیشنهاد» بزنید؛ بعد از تأیید صریح شما، هسته صفحه را واقعاً می‌خواند — بدون تأیید، هیچ صفحه‌ای باز نمی‌شود.',
          }),
        ),
      );
    } else if (drafts.length) {
      children.push(
        h(
          'div',
          { class: 'files-list card' },
          ...drafts.map((d) =>
            h(
              'div',
              { class: 'web-draft' },
              h(
                'button',
                {
                  class: 'files-row',
                  onclick: () => {
                    selected = d;
                    renderStage();
                  },
                },
                h('span', { class: 'files-row-ic', html: ic('globe') }),
                h(
                  'div',
                  { class: 'files-row-main' },
                  h('span', { class: 'files-row-name', text: d.title || d.url }),
                  h('span', { class: 'files-row-meta mono', text: d.url }),
                ),
                statusChip(d.status),
              ),
              d.status === 'APPROVAL_PENDING'
                ? h(
                    'div',
                    { class: 'web-draft-actions' },
                    h(
                      'button',
                      {
                        class: 'btn btn-primary btn-sm',
                        disabled: !!busy,
                        onclick: () => approve(d),
                      },
                      h('span', { html: ic('check') }),
                      'تأیید و بازخوانی',
                    ),
                    h(
                      'button',
                      { class: 'btn btn-sm', disabled: !!busy, onclick: () => deny(d) },
                      'رد',
                    ),
                  )
                : null,
            ),
          ),
        ),
      );
    }

    if (selected) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'PAGE EXCERPT' }),
          h('span', { class: 'files-preview-name mono', text: selected.url }),
          h('pre', { class: 'files-preview-text' }, selected.excerpt || '—'),
          h(
            'div',
            { class: 'result-meta' },
            statusChip(selected.status),
            selected.truncated
              ? h('span', { class: 'chip warn' }, h('span', { class: 'dot' }), 'گزینهٔ کوتاه‌شده')
              : null,
            h(
              'button',
              {
                class: 'btn btn-sm evidence-link',
                onclick: () =>
                  ctx.openEvidence({
                    title: 'بازخوانی وب',
                    steps: [
                      { name: 'browse.propose', detail: selected.url, meta: 'اسکن تزریق پرامپت' },
                      { name: 'تأیید انسانی', detail: 'کاربر', meta: 'human-in-the-loop' },
                      {
                        name: 'read_page',
                        detail: 'واکشی واقعی با محافظ SSRF',
                        meta: 'هسته پایتون',
                      },
                    ],
                  }),
              },
              h('span', { html: ic('evidence') }),
              'شواهد',
            ),
          ),
        ),
      );
      const links = selected.links || [];
      if (links.length) {
        children.push(
          h(
            'div',
            { class: 'result-panel card' },
            h('span', { class: 'micro', text: 'LINKS' }),
            h(
              'div',
              { class: 'files-list' },
              ...links.slice(0, 30).map((l) =>
                h(
                  'button',
                  {
                    class: 'files-row',
                    disabled: !!busy,
                    onclick: () => follow(l.url),
                  },
                  h('span', { class: 'files-row-ic', html: ic('arrow') }),
                  h(
                    'div',
                    { class: 'files-row-main' },
                    h('span', { class: 'files-row-name', text: l.url }),
                  ),
                  h('span', { class: 'chip' }, h('span', { class: 'dot' }), 'دنبال کردن'),
                ),
              ),
            ),
          ),
        );
      }
    }
    stage.replaceChildren(...children);
  }

  async function load() {
    try {
      const res = await api.browseList();
      drafts = res?.drafts ?? [];
      if (selected) {
        selected = drafts.find((d) => d.draft_id === selected.draft_id) || selected;
      }
    } catch (e) {
      drafts = [];
      error = msg(e);
    }
    renderStage();
  }

  async function propose() {
    const url = urlInput.value.trim();
    if (!url) return;
    busy = 'در حال بررسی نشانی…';
    error = null;
    renderStage();
    try {
      const res = await api.browsePropose(url);
      if (res?.draft_id) selected = res;
      urlInput.value = '';
      await load();
    } catch (e) {
      error = msg(e);
      renderStage();
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function approve(draft) {
    busy = `در حال بازخوانی ${draft.url}…`;
    error = null;
    renderStage();
    try {
      const res = await api.browseApprove(draft.draft_id);
      if (res?.draft_id) selected = res;
      await load();
    } catch (e) {
      error = msg(e);
      await load();
    } finally {
      busy = '';
      renderStage();
    }
  }

  async function deny(draft) {
    try {
      await api.browseDeny(draft.draft_id);
      await load();
    } catch (e) {
      error = msg(e);
      renderStage();
    }
  }

  async function follow(url) {
    if (!selected) return;
    busy = `در حال پیشنهاد ${url}…`;
    renderStage();
    try {
      const res = await api.browseFollow(selected.draft_id, url);
      if (res?.draft_id) selected = res;
      await load();
    } catch (e) {
      error = msg(e);
      renderStage();
    } finally {
      busy = '';
      renderStage();
    }
  }

  root.append(
    h(
      'div',
      { class: 'web-view' },
      h(
        'div',
        { class: 'voice-toolbar' },
        urlInput,
        h(
          'button',
          { class: 'btn btn-primary', onclick: propose },
          h('span', { html: ic('globe') }),
          'پیشنهاد',
        ),
      ),
      h(
        'span',
        { class: 'chip warn' },
        h('span', { class: 'dot' }),
        'هیچ صفحه‌ای بدون تأیید صریح شما بازخوانی نمی‌شود — بدون YOLO',
      ),
      stage,
    ),
  );

  renderStage();
  load();
}
