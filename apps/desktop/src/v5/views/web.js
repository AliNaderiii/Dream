/**
 * Web — two real, human-in-the-loop ways to reach the web:
 *  - «خواندن» (reading): the browse.* flow — propose a URL, approve it, only
 *    then the core fetches it (SSRF-guarded, prompt-injection-scanned).
 *  - «مرورگر» (browser): the REAL Playwright/CDP controller (webbrowser.*)
 *    — attach to your own Chrome or launch an isolated one; every navigation
 *    needs your explicit single-use approval (SEC-03), quota and blocklist
 *    enforced by the core. Nothing here is simulated.
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
  let mode = 'read'; // 'read' | 'browser'

  // ════════════════ pane 1: reading (browse.* — unchanged flow) ═══════════
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
              ? h('span', { class: 'chip warn' }, h('span', { class: 'dot' }), 'گزیدهٔ کوتاه‌شده')
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
              ...links
                .slice(0, 30)
                .map((l) =>
                  h(
                    'button',
                    { class: 'files-row', disabled: !!busy, onclick: () => follow(l.url) },
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

  const readPane = h(
    'div',
    { class: 'web-pane' },
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
  );

  // ════════════════ pane 2: real browser (webbrowser.*) ═══════════════════
  let wbStatus = null; // webbrowser.status result
  let wbError = null;
  let wbBusy = '';
  let pending = null; // approval_required session
  let page = null; // last PageContent
  let lastNav = { url: '', purpose: '' };

  const portInput = h('input', {
    class: 'input wb-port mono',
    dir: 'ltr',
    value: '9222',
    title: 'پورت دیباگ کروم — کروم باید با --remote-debugging-port=9222 اجرا شده باشد',
  });
  const navUrl = h('input', {
    class: 'input web-url',
    dir: 'ltr',
    placeholder: 'https://example.com',
  });
  const navPurpose = h('input', { class: 'input', placeholder: 'چرا این صفحه؟ (اختیاری)' });
  const selInput = h('input', {
    class: 'input mono',
    dir: 'ltr',
    placeholder: 'selector مثل button.submit',
  });
  const valInput = h('input', { class: 'input', placeholder: 'متنی که تایپ شود' });
  const wbStage = h('div', { class: 'web-stage' });

  function wbNotice(text, cls = 'err') {
    return h('div', { class: `notice ${cls}`, html: ic(cls === 'ok' ? 'check' : 'alert') }, text);
  }

  function renderBrowser() {
    const children = [];
    if (wbError) children.push(wbNotice(wbError));
    if (wbBusy) children.push(h('div', { class: 'notice', html: ic('refresh') }, wbBusy));

    if (wbStatus && !wbStatus.available) {
      children.push(
        wbNotice(`${wbStatus.error || 'موتور مرورگر نصب نیست'} — نصاب full دریم آن را همراه دارد.`),
      );
    } else if (wbStatus?.available) {
      const c = wbStatus.controller || {};
      children.push(
        h(
          'div',
          { class: 'result-meta' },
          h(
            'span',
            { class: `chip ${c.attached ? 'ok' : ''}` },
            h('span', { class: 'dot' }),
            c.attached
              ? c.attached_to_existing
                ? 'متصل به کروم شما'
                : 'مرورگر ایزوله فعال'
              : 'مرورگر بسته است',
          ),
          h(
            'span',
            { class: 'chip' },
            h('span', { class: 'dot' }),
            `سهمیه ناوبری: ${c.session_fetch_count ?? 0}/${c.max_fetches ?? 20}`,
          ),
          c.blocklist_error
            ? h(
                'span',
                { class: 'chip err' },
                h('span', { class: 'dot' }),
                'خطای بلاک‌لیست — همهٔ ناوبری‌ها رد می‌شوند',
              )
            : null,
          h(
            'button',
            { class: 'btn btn-sm', onclick: refreshWbStatus },
            h('span', { html: ic('refresh') }),
            'به‌روزرسانی وضعیت',
          ),
        ),
      );
    }

    // pending approval card — the SEC-03 human checkpoint
    if (pending) {
      children.push(
        h(
          'div',
          { class: 'result-panel card wb-approval' },
          h('span', { class: 'micro', text: 'APPROVAL REQUIRED' }),
          h('span', {
            class: 'empty-title',
            text: `ناوبری به «${pending.domain || '—'}» نیازمند تأیید شماست`,
          }),
          h('span', {
            class: 'empty-note',
            text: `هدف: ${pending.url || '—'}${pending.purpose ? ` — ${pending.purpose}` : ''}`,
          }),
          h('span', {
            class: 'empty-note',
            text: 'تأیید تک‌مصرف است و پس از ۱۵ دقیقه منقضی می‌شود.',
          }),
          h(
            'div',
            { class: 'voice-actions' },
            h(
              'button',
              {
                class: 'btn btn-primary',
                disabled: !!wbBusy,
                onclick: async () => {
                  await doApprove();
                },
              },
              h('span', { html: ic('check') }),
              'تأیید و رفتن',
            ),
            h(
              'button',
              {
                class: 'btn',
                disabled: !!wbBusy,
                onclick: async () => {
                  try {
                    await api.wbDeny(pending.id);
                  } catch {
                    /* already denied */
                  }
                  pending = null;
                  renderBrowser();
                },
              },
              'رد',
            ),
          ),
        ),
      );
    }

    if (page) {
      children.push(
        h(
          'div',
          { class: 'result-panel card' },
          h('span', { class: 'micro', text: 'CURRENT PAGE' }),
          h('span', { class: 'files-row-name', text: page.title || '—' }),
          h('span', { class: 'files-preview-name mono', text: page.url }),
          page.text ? h('pre', { class: 'files-preview-text' }, page.text.slice(0, 4000)) : null,
          (page.links || []).length
            ? h(
                'div',
                { class: 'result-meta' },
                h(
                  'span',
                  { class: 'chip' },
                  h('span', { class: 'dot' }),
                  `${page.links.length} پیوند در صفحه`,
                ),
              )
            : null,
          h(
            'div',
            { class: 'voice-actions' },
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  navUrl.value = page.url || '';
                  await doNavigate();
                },
              },
              h('span', { html: ic('refresh') }),
              'بازخوانی محتوا',
            ),
            h(
              'button',
              {
                class: 'btn btn-sm',
                onclick: async () => {
                  wbBusy = 'در حال گرفتن اسکرین‌شات…';
                  renderBrowser();
                  try {
                    const res = await api.wbScreenshot();
                    if (res?.success === false) wbError = res.error;
                    else
                      ctx.openEvidence({
                        title: 'اسکرین‌شات صفحه',
                        steps: [
                          {
                            name: 'webbrowser.screenshot',
                            detail: res.screenshot_path,
                            meta: 'فایل محلی',
                          },
                          { name: 'صفحه', detail: page.url, meta: page.title || '—' },
                        ],
                      });
                  } catch (e) {
                    wbError = msg(e);
                  } finally {
                    wbBusy = '';
                    renderBrowser();
                  }
                },
              },
              h('span', { html: ic('eye') }),
              'اسکرین‌شات کامل',
            ),
          ),
        ),
      );
    }

    wbStage.replaceChildren(...children);
  }

  async function refreshWbStatus() {
    try {
      wbStatus = await api.wbStatus();
      wbError = wbStatus?.available ? null : null;
    } catch (e) {
      wbStatus = null;
      wbError = msg(e);
    }
    renderBrowser();
  }

  async function doAttach() {
    wbBusy = 'در حال اتصال به کروم شما…';
    wbError = null;
    renderBrowser();
    try {
      const res = await api.wbAttach(Number(portInput.value) || 9222);
      if (res?.success === false) wbError = res.error;
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      await refreshWbStatus();
    }
  }

  async function doLaunch() {
    wbBusy = 'در حال اجرای مرورگر ایزوله…';
    wbError = null;
    renderBrowser();
    try {
      const res = await api.wbLaunch();
      if (res?.success === false) wbError = res.error;
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      await refreshWbStatus();
    }
  }

  async function doClose() {
    try {
      await api.wbClose();
      page = null;
      pending = null;
    } catch (e) {
      wbError = msg(e);
    }
    await refreshWbStatus();
  }

  async function doNavigate() {
    const url = navUrl.value.trim();
    if (!url) return;
    lastNav = { url, purpose: navPurpose.value.trim() };
    wbBusy = `در حال رفتن به ${url}…`;
    wbError = null;
    pending = null;
    renderBrowser();
    try {
      const res = await api.wbNavigate(url, lastNav.purpose);
      if (res?.success) {
        page = res.content;
      } else if (res?.status === 'approval_required' || res?.status === 'approval_expired') {
        pending = res.session || {};
        pending.purpose = lastNav.purpose;
      } else {
        wbError = res?.error || 'ناوبری ناموفق بود';
      }
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      renderBrowser();
      refreshWbStatus();
    }
  }

  async function doApprove() {
    if (!pending) return;
    wbBusy = 'در حال اعمال تأیید و رفتن…';
    renderBrowser();
    try {
      const res = await api.wbApprove(pending.id);
      pending = null;
      if (res?.success === false) {
        wbError = res.error;
      } else {
        const nav = await api.wbNavigate(lastNav.url, lastNav.purpose);
        if (nav?.success) page = nav.content;
        else if (nav?.status === 'approval_required' || nav?.status === 'approval_expired') {
          pending = nav.session || {};
        } else {
          wbError = nav?.error || 'ناوبری ناموفق بود';
        }
      }
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      renderBrowser();
      refreshWbStatus();
    }
  }

  async function doClick() {
    const selector = selInput.value.trim();
    if (!selector) return;
    wbBusy = `در حال کلیک روی ${selector}…`;
    wbError = null;
    renderBrowser();
    try {
      const res = await api.wbClick(selector);
      if (res?.success === false) wbError = res.error;
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      renderBrowser();
    }
  }

  async function doFill() {
    const selector = selInput.value.trim();
    if (!selector || !valInput.value) return;
    wbBusy = `در حال تایپ در ${selector}…`;
    wbError = null;
    renderBrowser();
    try {
      const res = await api.wbFill(selector, valInput.value);
      if (res?.success === false) wbError = res.error;
    } catch (e) {
      wbError = msg(e);
    } finally {
      wbBusy = '';
      renderBrowser();
    }
  }

  const browserPane = h(
    'div',
    { class: 'web-pane hidden' },
    h(
      'div',
      { class: 'voice-toolbar' },
      h(
        'label',
        { class: 'field wb-port-field' },
        h('span', { class: 'field-label', text: 'پورت کروم' }),
        portInput,
      ),
      h(
        'button',
        { class: 'btn btn-primary', onclick: doAttach },
        h('span', { html: ic('globe') }),
        'اتصال به کروم شما',
      ),
      h(
        'button',
        { class: 'btn', onclick: doLaunch },
        h('span', { html: ic('plus') }),
        'مرورگر ایزوله',
      ),
      h('button', { class: 'btn', onclick: doClose }, h('span', { html: ic('x') }), 'بستن'),
    ),
    h(
      'span',
      { class: 'empty-note' },
      'اتصال به کروم شما: کروم را با پرچم --remote-debugging-port=9222 اجرا کنید تا نشست‌ها و ورودهای‌تان بمانند. مرورگر ایزوله: یک کروم تازه و بدون پروفایل باز می‌شود.',
    ),
    h(
      'div',
      { class: 'voice-toolbar' },
      navUrl,
      navPurpose,
      h(
        'button',
        { class: 'btn btn-primary', onclick: doNavigate },
        h('span', { html: ic('arrow') }),
        'رفتن',
      ),
    ),
    h(
      'div',
      { class: 'voice-toolbar' },
      selInput,
      valInput,
      h('button', { class: 'btn', onclick: doClick }, h('span', { html: ic('check') }), 'کلیک'),
      h('button', { class: 'btn', onclick: doFill }, h('span', { html: ic('send') }), 'تایپ'),
    ),
    h(
      'span',
      { class: 'chip warn' },
      h('span', { class: 'dot' }),
      'هر ناوبری تأیید تک‌مصرف شما را می‌خواهد (SEC-03) · سهمیهٔ ۲۰ ناوبری · بلاک‌لیست دامنه',
    ),
    wbStage,
  );

  // ════════════════ tabs ══════════════════════════════════════════════════
  const readTab = h(
    'button',
    { class: 'voice-tab active', onclick: () => switchMode('read') },
    h('span', { html: ic('search') }),
    'خواندن',
  );
  const browserTab = h(
    'button',
    { class: 'voice-tab', onclick: () => switchMode('browser') },
    h('span', { html: ic('globe') }),
    'مرورگر',
  );

  function switchMode(next) {
    mode = next;
    readTab.classList.toggle('active', mode === 'read');
    browserTab.classList.toggle('active', mode === 'browser');
    readPane.classList.toggle('hidden', mode !== 'read');
    browserPane.classList.toggle('hidden', mode !== 'browser');
    if (mode === 'browser' && !wbStatus && !wbError) refreshWbStatus();
  }

  root.append(
    h(
      'div',
      { class: 'web-view' },
      h('div', { class: 'voice-tabs' }, readTab, browserTab),
      readPane,
      browserPane,
    ),
  );

  renderStage();
  load();
  renderBrowser();
}
