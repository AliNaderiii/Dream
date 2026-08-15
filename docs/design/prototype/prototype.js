/* Dream hi-fi prototype — Phase 0, Gates G5/G6.
 * Single-file interaction layer. No build step; open index.html.
 * Demonstrates: theme, RTL/FA, density, states, streaming, approval sheet,
 * memory explorer, subagent monitor, provenance tree, data workbench,
 * settings, onboarding, mobile tabs. */

"use strict";

/* ---------------- i18n ---------------- */
const STR = {
  en: {
    sessions: "Sessions", search: "Search sessions…", local_only: "local only",
    net_off: "network tools: off", agents_running: "2 subagents running",
    tab_chat: "Chat", tab_mem: "Memory", tab_agents: "Agents", tab_set: "Settings",
    today: "Today", yesterday: "Yesterday", pinned: "Pinned",
    s1: "Q3 report analysis", s2: "Car insurance renewal", s3: "Trip planning", s4: "Memory cleanup",
    chat_title: "Q3 report analysis",
    user_msg: "Summarise this CSV and chart revenue by month.",
    ctx: "Used 3 memories · 1 reminder",
    ai_text: "I loaded sales.csv (840 rows). Revenue peaks in March at $128k, dips in June, and recovers through Q3. Two rows had null revenue — I filled them with 0 and flagged them. Here's the monthly chart, and I can export a report if you'd like.",
    composer_ph: "Message Dream…  ( / for commands · @ to attach )",
    stop: "Stop", tool_running: "running", tool_ok: "ok", tool_blocked: "blocked",
    approval_title: "Dream wants to send an email",
    approval_sub: "Tool: send_email — external, irreversible · server: built-in",
    approval_note: "If allowed, this leaves your machine. Deny returns a structured refusal to the model.",
    deny: "Deny", allow_once: "Allow once", always_allow: "Always allow…",
    denied_toast: "Denied — the model was told why", allowed_toast: "Allowed once — running send_email",
    mem_title: "Memory", mem_search: "Search memories — «كتاب» finds «کتاب»",
    kind_semantic: "semantic", kind_episodic: "episodic", kind_procedural: "procedural",
    matched_norm: "matched via normalized form",
    mem_detail: "Detail", importance: "Importance", used: "Used", turns_used: "Turns that used this memory",
    edit: "Edit", del: "Delete", dedupe: "Dedupe (dry-run)…",
    empty_mem_t: "No memories yet", empty_mem_d: "Dream distills facts from conversations, or add one manually.",
    add_memory: "Add memory",
    sub_title: "Subagent monitor", cancel: "Cancel", open_log: "Open log", review: "Review & accept",
    accepted_toast: "Output posted to parent conversation",
    empty_sub_t: "No subagents yet", empty_sub_d: "Ask Dream to work in the background, or use /spawn.",
    prov_title: "Provenance — Run #42", prov_selected: "Selected artifact",
    export_bundle: "Export provenance bundle", rerun: "Re-run on new file…",
    data_title: "Data workbench — sales.csv", data_banner: "Previewing 8 of 840 rows — operations run on the full file",
    steps: "Steps", view_code: "view code", revert: "revert",
    chart_builder: "Chart: revenue by month", export_report: "Export report ▾",
    set_title: "Settings", set_general: "General", set_appearance: "Appearance", set_providers: "Providers",
    set_perms: "Permissions", theme: "Theme", light: "Light", dark: "Dark", density: "Density",
    comfortable: "Comfortable", compact: "Compact", lang: "Language", reduce_motion: "Reduce motion",
    numerals: "Persian numerals (۱۲۳)", cal: "Jalali calendar primary",
    lang_changed: "Language changed", undo: "Undo",
    onb1_t: "Welcome to Dream", onb1_d: "Your local-first assistant. Choose your language and look.",
    onb2_t: "Choose a provider", onb2_d: "Dream works fully offline. Add a model provider now or later.",
    onb3_t: "Privacy defaults", onb3_d: "You are in control. These can change anytime in Settings.",
    onb_ollama: "Ollama (local) — detected ✓", onb_openai: "OpenAI-compatible — needs key",
    onb_offline: "Offline echo — try Dream with no setup",
    onb_net: "Network tools", onb_ask: "Ask before every dangerous action", onb_where: "Data stays in ~/.dream",
    back: "Back", next: "Next", skip: "Skip", finish: "Finish",
    err_title: "Couldn't reach Ollama at localhost:11434",
    err_d: "The provider did not respond within 10s.", retry: "Retry", switch_provider: "Switch provider",
    loading: "Loading…", provenance: "provenance", reminder_chip: "Reminder: بیمه renewal due Mehr 15",
  },
  fa: {
    sessions: "جلسه‌ها", search: "…جستجوی جلسه‌ها", local_only: "فقط محلی",
    net_off: "ابزارهای شبکه: خاموش", agents_running: "۲ زیرعامل در حال اجرا",
    tab_chat: "گفتگو", tab_mem: "حافظه", tab_agents: "عامل‌ها", tab_set: "تنظیمات",
    today: "امروز", yesterday: "دیروز", pinned: "سنجاق‌شده",
    s1: "تحلیل گزارش سه‌ماهه", s2: "تمدید بیمه ماشین", s3: "برنامه سفر", s4: "پاک‌سازی حافظه",
    chat_title: "تحلیل گزارش سه‌ماهه",
    user_msg: "این فایل CSV را خلاصه کن و نمودار درآمد ماهانه بکش.",
    ctx: "۳ حافظه · ۱ یادآور استفاده شد",
    ai_text: "فایل sales.csv را خواندم (۸۴۰ ردیف). درآمد در اسفند به اوج می‌رسد، در خرداد افت می‌کند و در پاییز بهبود می‌یابد. دو ردیف مقدار خالی داشتند که با صفر پر و علامت‌گذاری شدند. نمودار ماهانه آماده است؛ اگر بخواهی گزارش کامل خروجی می‌گیرم.",
    composer_ph: "…پیامی برای دریم بنویس ( / برای دستورها )",
    stop: "توقف", tool_running: "در حال اجرا", tool_ok: "موفق", tool_blocked: "مسدود",
    approval_title: "دریم می‌خواهد ایمیل بفرستد",
    approval_sub: "ابزار: send_email — بیرونی و برگشت‌ناپذیر · سرور: داخلی",
    approval_note: "در صورت اجازه، این پیام از دستگاه شما خارج می‌شود. ردکردن، دلیلِ ساختاریافته به مدل برمی‌گرداند.",
    deny: "رد کن", allow_once: "یک‌بار اجازه بده", always_allow: "…همیشه اجازه بده",
    denied_toast: "رد شد — دلیل به مدل اعلام شد", allowed_toast: "یک‌بار اجازه داده شد — ارسال ایمیل",
    mem_title: "حافظه", mem_search: "جستجوی حافظه — «كتاب» همان «کتاب» را می‌یابد",
    kind_semantic: "معنایی", kind_episodic: "رویدادی", kind_procedural: "روالی",
    matched_norm: "تطبیق با صورت نرمال‌شده",
    mem_detail: "جزئیات", importance: "اهمیت", used: "استفاده", turns_used: "نوبت‌هایی که از این حافظه استفاده کردند",
    edit: "ویرایش", del: "حذف", dedupe: "…حذف تکراری‌ها (آزمایشی)",
    empty_mem_t: "هنوز حافظه‌ای نیست", empty_mem_d: "دریم از گفتگوها واقعیت‌ها را استخراج می‌کند؛ یا خودتان اضافه کنید.",
    add_memory: "افزودن حافظه",
    sub_title: "پایشگر زیرعامل‌ها", cancel: "لغو", open_log: "نمایش لاگ", review: "بررسی و پذیرش",
    accepted_toast: "خروجی به گفتگوی اصلی افزوده شد",
    empty_sub_t: "هنوز زیرعاملی نیست", empty_sub_d: "از دریم بخواهید در پس‌زمینه کار کند یا /spawn را بزنید.",
    prov_title: "پیشینه — اجرای ۴۲", prov_selected: "مصنوع انتخاب‌شده",
    export_bundle: "خروجی بسته پیشینه", rerun: "…اجرای دوباره با فایل تازه",
    data_title: "میز داده — sales.csv", data_banner: "نمایش ۸ از ۸۴۰ ردیف — عملیات روی کل فایل اجرا می‌شود",
    steps: "گام‌ها", view_code: "کد", revert: "واگرد",
    chart_builder: "نمودار: درآمد ماهانه", export_report: "▾ خروجی گزارش",
    set_title: "تنظیمات", set_general: "عمومی", set_appearance: "ظاهر", set_providers: "ارائه‌دهنده‌ها",
    set_perms: "مجوزها", theme: "پوسته", light: "روشن", dark: "تیره", density: "تراکم",
    comfortable: "راحت", compact: "فشرده", lang: "زبان", reduce_motion: "کاهش پویانمایی",
    numerals: "اعداد فارسی (۱۲۳)", cal: "تقویم جلالی به‌عنوان اصلی",
    lang_changed: "زبان تغییر کرد", undo: "واگرد",
    onb1_t: "به دریم خوش آمدید", onb1_d: "دستیار محلی شما. زبان و ظاهر را انتخاب کنید.",
    onb2_t: "انتخاب ارائه‌دهنده", onb2_d: "دریم کاملاً آفلاین کار می‌کند. اکنون یا بعداً مدل اضافه کنید.",
    onb3_t: "پیش‌فرض‌های حریم خصوصی", onb3_d: "کنترل با شماست. هر زمان در تنظیمات قابل تغییر است.",
    onb_ollama: "اولاما (محلی) — یافت شد ✓", onb_openai: "سازگار با OpenAI — نیازمند کلید",
    onb_offline: "پژواک آفلاین — بدون هیچ تنظیمی امتحان کنید",
    onb_net: "ابزارهای شبکه", onb_ask: "پیش از هر کار خطرناک بپرس", onb_where: "داده‌ها در ‎~/.dream می‌ماند",
    back: "قبلی", next: "بعدی", skip: "رد شدن", finish: "پایان",
    err_title: "اتصال به اولاما در localhost:11434 برقرار نشد",
    err_d: "ارائه‌دهنده در ۱۰ ثانیه پاسخ نداد.", retry: "تلاش دوباره", switch_provider: "تغییر ارائه‌دهنده",
    loading: "…در حال بارگذاری", provenance: "پیشینه", reminder_chip: "یادآور: تمدید بیمه تا ۱۵ مهر",
  },
};

const state = { theme: "light", lang: "en", density: "comfortable", uistate: "happy", view: "chat" };
const t = (k) => (STR[state.lang][k] ?? STR.en[k] ?? k);
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

/* ---------------- demo bar wiring ---------------- */
function wireGroup(id, key, fn) {
  $("#" + id).addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]"); if (!b) return;
    $$("#" + id + " button").forEach((x) => x.classList.toggle("on", x === b));
    state[key] = b.dataset.v; fn(b.dataset.v);
  });
}
wireGroup("gTheme", "theme", (v) => document.documentElement.dataset.theme = v);
wireGroup("gLang", "lang", (v) => {
  document.documentElement.lang = v;
  document.documentElement.dir = v === "fa" ? "rtl" : "ltr";
  render(); applyStatic();
});
wireGroup("gDensity", "density", (v) =>
  document.documentElement.style.setProperty("--density-scale", v === "compact" ? "0.75" : "1"));
wireGroup("gState", "uistate", () => render());
$("#btnOnb").addEventListener("click", () => showOnboarding());
$("#btnApproval").addEventListener("click", () => openApproval());

function applyStatic() {
  $$("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  $$("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
  $("#sbAgents").textContent = t("agents_running");
}

/* ---------------- navigation ---------------- */
document.addEventListener("click", (e) => {
  const nav = e.target.closest(".rail button[data-view], .tabbar button[data-view]");
  if (nav) {
    state.view = nav.dataset.view;
    $$(".rail button[data-view], .tabbar button[data-view]").forEach((b) =>
      b.classList.toggle("on", b.dataset.view === state.view));
    render();
  }
});

/* ---------------- session sidebar ---------------- */
function renderSidebar() {
  const L = $("#sessionList");
  L.innerHTML = `
    <div class="group-label">${t("pinned")}</div>
    <button class="srow"><span class="t">★ ${t("s2")}</span></button>
    <div class="group-label">${t("today")}</div>
    <button class="srow on"><span class="dot"></span><span class="t">${t("s1")}</span></button>
    <button class="srow"><span class="t">${t("s2")}</span></button>
    <div class="group-label">${t("yesterday")}</div>
    <button class="srow"><span class="t">${t("s3")}</span></button>
    <button class="srow"><span class="t">${t("s4")}</span></button>`;
}

/* ---------------- shared bits ---------------- */
const riskChip = (tier) => {
  const lbl = { safe: state.lang === "fa" ? "ایمن" : "safe", guarded: state.lang === "fa" ? "محافظت‌شده" : "guarded", dangerous: state.lang === "fa" ? "خطرناک" : "dangerous" }[tier];
  const icon = { safe: "M12 3l7 3v5c0 4.4-3 8.4-7 10-4-1.6-7-5.6-7-10V6z M9.5 12l2 2 3.5-3.5", guarded: "M12 3l7 3v5c0 4.4-3 8.4-7 10-4-1.6-7-5.6-7-10V6z M12 9v3 M12 15h.01", dangerous: "M12 3l7 3v5c0 4.4-3 8.4-7 10-4-1.6-7-5.6-7-10V6z M10 10l4 4 M14 10l-4 4" }[tier];
  return `<span class="chip risk-${tier}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="${icon}"/></svg>${lbl}</span>`;
};
const kindChip = (k) => `<span class="chip kind-${k}">${t("kind_" + k)}</span>`;

function toast(msg, undo) {
  $$(".toast").forEach((x) => x.remove());
  const d = document.createElement("div");
  d.className = "toast";
  d.innerHTML = `<span>${msg}</span>${undo ? `<button class="undo">${t("undo")}</button>` : ""}`;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 5000);
}

/* ---------------- views ---------------- */
const W = () => $("#workspace");

function stateWrap(happyHTML, opts = {}) {
  if (state.uistate === "loading")
    return `<div class="page"><div class="page-grid">
      <div class="skeleton" style="height:36px;width:40%"></div>
      <div class="skeleton" style="height:120px"></div>
      <div class="skeleton" style="height:120px;width:80%"></div>
      <div class="skeleton" style="height:60px;width:60%"></div></div></div>`;
  if (state.uistate === "error")
    return `<div class="page"><div class="error-card">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>
      <div style="flex:1"><strong>${t("err_title")}</strong>
        <div style="font-size:var(--fs-caption);margin:4px 0 10px">${t("err_d")}</div>
        <div style="display:flex;gap:8px"><button class="btn btn-secondary">${t("retry")}</button>
        <button class="btn btn-ghost">${t("switch_provider")}</button></div></div></div></div>`;
  if (state.uistate === "empty" && opts.empty) return opts.empty;
  return happyHTML;
}

/* ----- chat ----- */
function viewChat() {
  const empty = `<div class="pane-head"><h1>${t("chat_title")}</h1></div>
  <div class="empty-state">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/></svg>
    <h3>${state.lang === "fa" ? "هر چه می‌خواهی بپرس — آنچه مهم است را به خاطر می‌سپارم." : "Ask me anything — I remember what matters."}</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
      <button class="btn btn-secondary">${state.lang === "fa" ? "خلاصه یک CSV ←" : "Summarise a CSV →"}</button>
      <button class="btn btn-secondary">${state.lang === "fa" ? "یادآوری تمدید بیمه ←" : "Remind me: insurance →"}</button>
    </div></div>${composerHTML()}`;

  const happy = `
  <div class="pane-head"><h1>${t("chat_title")}</h1>
    <span class="chip chip-plain">qwen2.5:7b</span>
    <button class="btn btn-ghost" title="Split pane">⫲</button></div>
  <div class="transcript" id="transcript">
    <div class="msg-user">${t("user_msg")}</div>
    <div class="turn">
      <button class="ctx-chip" id="ctxChip"><span>❯</span> ${t("ctx")}</button>
      <div class="ctx-detail" id="ctxDetail">
        <div class="mrow">${kindChip("semantic")}<span style="unicode-bidi:isolate">${state.lang === "fa" ? "قهوه تلخ را ترجیح می‌دهم" : "I prefer dark coffee"}</span><span class="score">0.83</span></div>
        <div class="mrow">${kindChip("semantic")}<span style="unicode-bidi:isolate">${state.lang === "fa" ? "بیمه‌نامه A-102 تا ۱۵ مهر" : "Policy #A-102 expires Mehr 15"}</span><span class="score">0.71</span></div>
        <div class="mrow">${kindChip("procedural")}<span style="unicode-bidi:isolate">${state.lang === "fa" ? "برای بیمه دو زبانه پاسخ بده" : "Answer bilingual for insurance"}</span><span class="score">0.64</span></div>
        <div class="mrow"><span class="chip chip-plain">⏰</span><span>${t("reminder_chip")}</span></div>
      </div>
      <div class="tool-card" data-tool>
        <header><span class="status ok"></span><span class="name">read_file(path="…/sales.csv")</span>
          ${riskChip("guarded")}<span class="st-label">${t("tool_ok")} · 0.4s</span></header>
        <div class="body">→ {"rows": 840, "columns": ["date","region","revenue","notes"], "issues": {"revenue": "2 nulls"}}</div>
      </div>
      <div class="tool-card" data-tool>
        <header><span class="status running"></span><span class="name">run_analysis(steps=4)</span>
          ${riskChip("safe")}<span class="st-label">${t("tool_running")}</span></header>
        <div class="body">step 3/4: aggregate by month …</div>
      </div>
      <div class="msg-ai"><span id="aiText"></span><span class="caret" id="caret"></span></div>
      <div class="turn-foot"><span>qwen2.5:7b</span><span class="num">4.2s · 812 tok</span><a href="#" data-goto="provenance">${t("provenance")} ↗</a></div>
    </div>
  </div>${composerHTML(true)}
  <div class="scrim" id="scrim"></div>
  ${approvalHTML()}`;

  W().innerHTML = stateWrap(happy, { empty });
  if (state.uistate === "happy") {
    // streaming animation
    const words = t("ai_text").split(" "); let i = 0;
    const el = $("#aiText"), caret = $("#caret");
    const iv = setInterval(() => {
      if (!document.body.contains(el)) return clearInterval(iv);
      el.textContent = words.slice(0, ++i).join(" ") + " ";
      const tr = $("#transcript"); if (tr) tr.scrollTop = tr.scrollHeight;
      if (i >= words.length) { clearInterval(iv); caret?.remove(); setSend(false); }
    }, 60);
    setSend(true);
    $("#ctxChip")?.addEventListener("click", () => $("#ctxDetail").classList.toggle("open"));
    $$("[data-tool] header").forEach((h) => h.addEventListener("click", () => h.parentElement.classList.toggle("open")));
    $$("[data-goto]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); state.view = "provenance"; render(); }));
    wireApproval();
  }
}
function composerHTML(withStop) {
  return `<div class="composer-wrap"><div class="composer">
    <input placeholder="${t("composer_ph")}" aria-label="Message">
    <div class="row">
      <span class="chip chip-plain">qwen2.5:7b ▾</span>
      <span class="chip chip-plain">＋</span>
      <button class="send" id="sendBtn" aria-label="Send">
        <svg class="dir" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
      </button>
    </div></div></div>`;
}
function setSend(streaming) {
  const b = $("#sendBtn"); if (!b) return;
  b.innerHTML = streaming
    ? `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="1.5"/></svg>`
    : `<svg class="dir" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`;
  b.title = streaming ? t("stop") : "";
}

/* ----- approval sheet ----- */
function approvalHTML() {
  return `<div class="sheet" id="sheet" role="alertdialog" aria-modal="true" aria-labelledby="shTitle">
    ${riskChip("dangerous")}
    <h3 id="shTitle">${t("approval_title")}</h3>
    <div class="sub">${t("approval_sub")}</div>
    <div class="args">to: agent@insurer.example
subject: "Renewal request A-102"
body: 1.2 KB ▸</div>
    <div class="note">${t("approval_note")}</div>
    <div class="acts">
      <button class="btn btn-secondary" id="shDeny">${t("deny")} <kbd style="font-size:10px;opacity:.6">Esc</kbd></button>
      <span class="spacer"></span>
      <button class="btn btn-ghost">${t("always_allow")}</button>
      <button class="btn btn-primary" id="shAllow">${t("allow_once")} <kbd style="font-size:10px;opacity:.7">⏎</kbd></button>
    </div></div>`;
}
function wireApproval() {
  $("#shDeny")?.addEventListener("click", () => closeApproval(t("denied_toast")));
  $("#shAllow")?.addEventListener("click", () => closeApproval(t("allowed_toast")));
  $("#scrim")?.addEventListener("click", () => closeApproval(t("denied_toast")));
}
function openApproval() {
  if (state.view !== "chat" || state.uistate !== "happy") { state.view = "chat"; $$(".rail button[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === "chat")); state.uistate = "happy"; render(); }
  requestAnimationFrame(() => { $("#scrim")?.classList.add("on"); $("#sheet")?.classList.add("on"); $("#shAllow")?.focus(); });
  document.addEventListener("keydown", escClose);
}
function closeApproval(msg) {
  $("#scrim")?.classList.remove("on"); $("#sheet")?.classList.remove("on");
  document.removeEventListener("keydown", escClose);
  if (msg) toast(msg);
}
function escClose(e) { if (e.key === "Escape") closeApproval(t("denied_toast")); if (e.key === "Enter" && $("#sheet")?.classList.contains("on")) closeApproval(t("allowed_toast")); }

/* ----- memory ----- */
function viewMemory() {
  const mems = state.lang === "fa" ? [
    ["semantic", "قهوه تلخ را ترجیح می‌دهم", "۳ روز", true],
    ["episodic", "به کافه‌ای در تهران رفتم", "۳ روز", false],
    ["procedural", "برای بیمه همیشه دو زبانه پاسخ بده", "۱ هفته", false],
    ["semantic", "بیمه‌نامه A-102 تا ۱۵ مهر اعتبار دارد ★", "۲ هفته", false],
  ] : [
    ["semantic", "I prefer dark coffee", "3d", true],
    ["episodic", "Visited Tehran coffee shop", "3d", false],
    ["procedural", "Always answer bilingual for insurance", "1w", false],
    ["semantic", "Policy #A-102 expires Mehr 15 ★", "2w", false],
  ];
  const empty = `<div class="pane-head"><h1>${t("mem_title")}</h1></div>
    <div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2z"/><path d="M4 17h15"/></svg>
      <h3>${t("empty_mem_t")}</h3><p>${t("empty_mem_d")}</p>
      <button class="btn btn-primary">＋ ${t("add_memory")}</button></div>`;
  const happy = `
  <div class="pane-head"><h1>${t("mem_title")}</h1>
    <button class="btn btn-secondary">${t("dedupe")}</button>
    <button class="btn btn-primary">＋ ${t("add_memory")}</button></div>
  <div class="page"><div class="mem-layout">
    <div>
      <input class="input" style="margin-bottom:var(--sp-3)" placeholder="${t("mem_search")}">
      ${mems.map(([k, txt, age, norm], i) => `
        <button class="mem-row ${i === 0 ? "on" : ""}">${kindChip(k)}
          <span class="txt">${txt}</span>
          ${norm ? `<span class="match-badge">${t("matched_norm")}</span>` : ""}
          <span class="age">${age}</span></button>`).join("")}
    </div>
    <div class="card">
      <h3>${t("mem_detail")}</h3>
      <p style="unicode-bidi:isolate">${mems[0][1]}</p>
      <div class="meta" style="margin-top:var(--sp-3)">${t("importance")} · 0.7</div>
      <div class="imp-track"><div class="imp-fill" style="width:70%"></div></div>
      <div class="meta">${t("used")}: <span class="ltr-island" style="font-family:inherit">12×</span> · score 0.83</div>
      <div class="meta" style="margin-top:var(--sp-3);font-weight:600">${t("turns_used")}</div>
      <div class="meta">“${state.lang === "fa" ? "قهوه سفارش بده" : "order coffee"}” ↗ · “${state.lang === "fa" ? "صبحانه" : "breakfast plan"}” ↗</div>
      <div style="display:flex;gap:8px;margin-top:var(--sp-4)">
        <button class="btn btn-secondary">${t("edit")}</button>
        <button class="btn btn-ghost" style="color:var(--danger-fg)">${t("del")}</button>
      </div>
    </div>
  </div></div>`;
  W().innerHTML = stateWrap(happy, { empty });
}

/* ----- subagents ----- */
function viewSubagents() {
  const A = state.lang === "fa" ? [
    ["#۳ تحقیق قیمت بیمه", "در حال اجرا", "02:41", "12.4k", "running"],
    ["#۲ خلاصه PDF", "تمام شد ✓", "01:12", "8.1k", "done"],
    ["#۱ پاک‌سازی داده", "لغو شد", "00:33", "2.0k", "cancelled"],
  ] : [
    ["#3 Research insurance quotes", "running", "02:41", "12.4k", "running"],
    ["#2 Summarise PDF", "finished ✓", "01:12", "8.1k", "done"],
    ["#1 Data cleanup", "cancelled", "00:33", "2.0k", "cancelled"],
  ];
  const empty = `<div class="pane-head"><h1>${t("sub_title")}</h1></div>
    <div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="7" width="14" height="11" rx="2"/><path d="M12 7V4M8 11h.01M16 11h.01M9 15h6"/></svg>
    <h3>${t("empty_sub_t")}</h3><p>${t("empty_sub_d")}</p></div>`;
  const happy = `
  <div class="pane-head"><h1>${t("sub_title")}</h1></div>
  <div class="page"><div class="sub-grid">
    ${A.map(([n, st, el, tok, cls]) => `
      <div class="card">
        <h3 style="unicode-bidi:isolate">${n}</h3>
        <div class="meta"><span class="status ${cls === "running" ? "running" : cls === "done" ? "ok" : "error"}" style="display:inline-block;width:8px;height:8px;border-radius:99px;margin-inline-end:6px"></span>${st} · <span class="elapsed">${el}</span> · <span class="elapsed">${tok} tok</span></div>
        <div class="meta ltr-island" style="margin-top:6px">[tool] search_web("بیمه quotes") → ok</div>
        <div style="display:flex;gap:8px;margin-top:var(--sp-3)">
          <button class="btn btn-secondary" data-log>${t("open_log")}</button>
          ${cls === "running" ? `<button class="btn btn-ghost" style="color:var(--danger-fg)">${t("cancel")}</button>` : cls === "done" ? `<button class="btn btn-primary" data-accept>${t("review")}</button>` : ""}
        </div>
      </div>`).join("")}
  </div>
  <div class="card" style="margin-top:var(--sp-4)">
    <h3 class="ltr-island" style="font-family:var(--font-latin)">Log — #3 Research insurance quotes</h3>
    <div class="log">[12:01:04] turn 1 · plan: find 3 insurers, compare premiums
[12:01:06] [tool] search_web(query='بیمه ماشین قیمت') -> ok
[12:01:09] [tool] read_page(address='https://…') -> ok
[12:01:14] streaming: 'اولین گزینه بیمه…'
<span class="err">[12:01:20] [tool] read_page(…) -> error: timeout — retrying (1/2)</span></div>
  </div></div>`;
  W().innerHTML = stateWrap(happy, { empty });
  $$("[data-accept]").forEach((b) => b.addEventListener("click", () => toast(t("accepted_toast"))));
}

/* ----- provenance ----- */
function viewProvenance() {
  const N = state.lang === "fa" ? [
    [0, "اجرای ۴۲ (جلسه: گزارش سه‌ماهه) · 12:01–12:06", false],
    [1, "نوبت ۱ — «این CSV را خلاصه کن»", false],
    [2, "read_file(sales.csv) → ok", true],
    [3, "مصنوع: پیش‌نمایش جدول t1#", false],
    [1, "نوبت ۲ — «نمودار درآمد»", false],
    [2, "run_analysis(step 1..4) → ok", true],
    [3, "مصنوع: نمودار c1# (درآمد ماهانه) ✦", false],
    [1, "زیرعامل ۳# — تحقیق قیمت ↗", false],
  ] : [
    [0, "Run #42 (session: Q3 report) · 12:01–12:06", false],
    [1, "Turn 1 — “summarise this CSV”", false],
    [2, "read_file(sales.csv) → ok", true],
    [3, "artifact: table preview #t1", false],
    [1, "Turn 2 — “chart revenue”", false],
    [2, "run_analysis(step 1..4) → ok", true],
    [3, "artifact: chart #c1 (revenue by month) ✦", false],
    [1, "Subagent #3 — quotes research ↗ (linked run)", false],
  ];
  const happy = `
  <div class="pane-head"><h1>${t("prov_title")}</h1>
    <button class="btn btn-secondary">${t("export_bundle")}</button>
    <button class="btn btn-primary">${t("rerun")}</button></div>
  <div class="page"><div class="mem-layout">
    <div class="card prov-tree">
      ${N.map(([d, s, mono], i) => `
        <div class="prov-node ${i === 6 ? "sel" : ""}" style="padding-inline-start:${d * 20}px">
          <span class="glyph">${d === 0 ? "▣" : d === 1 ? "◈" : d === 2 ? "⚙" : "◍"}</span>
          <button><span class="lbl ${mono ? "mono" : ""}">${s}</span></button>
        </div>`).join("")}
    </div>
    <div class="card">
      <h3>${t("prov_selected")}: <span class="ltr-island" style="font-family:var(--font-mono)">chart #c1</span></h3>
      <div class="chart-slot" aria-hidden="true">
        ${[52, 84, 128, 96, 60, 44, 72, 88, 104].map((v, i) => `<div class="bar" style="height:${v}px;background:var(--chart-${(i % 8) + 1})"></div>`).join("")}
      </div>
      <div class="meta ltr-island">produced by: run_analysis · turn 2 · step 4</div>
      <div class="meta ltr-island">input: sales.csv (sha256 1f0a…) rows 1–840</div>
      <div style="display:flex;gap:8px;margin-top:var(--sp-3)">
        <button class="btn btn-secondary">PNG</button><button class="btn btn-secondary">SVG</button>
        <button class="btn btn-ghost">${t("view_code")}</button>
      </div>
    </div>
  </div></div>`;
  W().innerHTML = stateWrap(happy);
}

/* ----- data workbench ----- */
function viewData() {
  const rows = [
    ["2026-01-04", "north", "12,400", ""],
    ["2026-01-11", "south", "9,850", ""],
    ["2026-01-18", "north", "", "⚠ null"],
    ["2026-01-25", "east", "14,020", ""],
    ["2026-02-01", "south", "11,300", ""],
    ["2026-02-08", "west", "8,120", ""],
    ["2026-02-15", "north", "13,480", ""],
    ["2026-02-22", "east", "10,760", ""],
  ];
  const steps = state.lang === "fa"
    ? [["۱", "تبدیل date به datetime", "done"], ["۲", "پر کردن خالی‌ها با ۰", "done"], ["۳", "حذف ستون notes", "done"], ["۴", "تجمیع ماهانه", "running"], ["۵", "نمودار درآمد/ماه", "queued"]]
    : [["1", "cast date → datetime", "done"], ["2", "fill nulls revenue=0", "done"], ["3", "drop column notes", "done"], ["4", "aggregate by month", "running"], ["5", "chart revenue/month", "queued"]];
  const happy = `
  <div class="pane-head"><h1>${t("data_title")}</h1>
    <button class="btn btn-primary">${t("export_report")}</button></div>
  <div class="page"><div class="data-layout">
    <div class="card" style="grid-row:span 2;overflow:auto">
      <div class="meta" style="margin-bottom:var(--sp-2)">${t("data_banner")}</div>
      <table class="grid-table">
        <thead><tr><th>date 📅</th><th>region Aa</th><th>revenue #</th><th>notes</th></tr></thead>
        <tbody>${rows.map((r) => `<tr>${r.map((c, i) =>
          `<td class="${c.startsWith("⚠") || (i === 2 && c === "") ? "cell-issue" : ""}">${c || (i === 2 ? "⚠ null" : "")}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
    <div class="card">
      <h3>${t("steps")}</h3>
      ${steps.map(([n, s, st]) => `
        <div class="step-row ${st === "running" ? "running" : ""}">
          <span class="n">${n}</span><span style="flex:1;unicode-bidi:isolate">${s}</span>
          ${st === "done" ? `<span style="color:var(--success-fg)">✓</span>` : st === "running" ? `<span class="status running" style="width:8px;height:8px;border-radius:99px"></span>` : `<span class="meta">…</span>`}
          <button class="revert" title="${t("revert")}">↩</button>
        </div>`).join("")}
      <button class="btn btn-ghost" style="font-size:var(--fs-caption)">${t("view_code")} ↗</button>
    </div>
    <div class="card">
      <h3>${t("chart_builder")}</h3>
      <div class="chart-slot">
        ${[52, 84, 128, 96, 60, 44].map((v, i) => `<div class="bar" style="height:${v}px;background:var(--chart-${(i % 8) + 1})"></div>`).join("")}
      </div>
    </div>
  </div></div>`;
  W().innerHTML = stateWrap(happy);
}

/* ----- settings ----- */
function viewSettings() {
  const happy = `
  <div class="pane-head"><h1>${t("set_title")}</h1></div>
  <div class="page"><div class="set-layout">
    <nav class="set-nav">
      <button>${t("set_general")}</button>
      <button class="on">${t("set_appearance")}</button>
      <button>${t("set_providers")}</button>
      <button>MCP</button>
      <button>${t("set_perms")}</button>
    </nav>
    <div>
      <div class="set-row"><div class="lbl"><div>${t("theme")}</div></div>
        <div style="display:flex;gap:8px">
          <div class="theme-tile ${state.theme === "light" ? "on" : ""}" data-th="light" style="background:#F8F8FA;color:#212129">${t("light")}</div>
          <div class="theme-tile ${state.theme === "dark" ? "on" : ""}" data-th="dark" style="background:#141419;color:#ECECF1">${t("dark")}</div>
        </div></div>
      <div class="set-row"><div class="lbl"><div>${t("density")}</div></div>
        <span class="chip ${state.density === "comfortable" ? "chip-plain" : ""}" style="cursor:pointer" data-dn="comfortable">${t("comfortable")}</span>
        <span class="chip ${state.density === "compact" ? "chip-plain" : ""}" style="cursor:pointer" data-dn="compact">${t("compact")}</span></div>
      <div class="set-row"><div class="lbl"><div>${t("lang")}</div><div class="d">English / فارسی</div></div>
        <button class="btn btn-secondary" id="setLang">${state.lang === "en" ? "فارسی" : "English"}</button></div>
      <div class="set-row"><div class="lbl"><div>${t("numerals")}</div></div><div class="switch ${state.lang === "fa" ? "on" : ""}"></div></div>
      <div class="set-row"><div class="lbl"><div>${t("cal")}</div></div><div class="switch ${state.lang === "fa" ? "on" : ""}"></div></div>
      <div class="set-row"><div class="lbl"><div>${t("reduce_motion")}</div><div class="d">prefers-reduced-motion</div></div><div class="switch"></div></div>
    </div>
  </div></div>`;
  W().innerHTML = stateWrap(happy);
  $$(".theme-tile").forEach((el) => el.addEventListener("click", () => {
    state.theme = el.dataset.th; document.documentElement.dataset.theme = state.theme;
    $$("#gTheme button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.theme));
    viewSettings();
  }));
  $$("[data-dn]").forEach((el) => el.addEventListener("click", () => {
    state.density = el.dataset.dn;
    document.documentElement.style.setProperty("--density-scale", state.density === "compact" ? "0.75" : "1");
    $$("#gDensity button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.density));
    viewSettings();
  }));
  $("#setLang")?.addEventListener("click", () => {
    state.lang = state.lang === "en" ? "fa" : "en";
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
    $$("#gLang button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.lang));
    render(); applyStatic(); toast(t("lang_changed"), true);
  });
  $$(".switch").forEach((s) => s.addEventListener("click", () => s.classList.toggle("on")));
}

/* ----- onboarding ----- */
let onbStep = 0;
function showOnboarding() { onbStep = 0; renderOnb(); }
function renderOnb() {
  $("#onb")?.remove();
  const d = document.createElement("div");
  d.className = "onb"; d.id = "onb";
  const steps = [
    `<h2>${t("onb1_t")}</h2><p class="lead">${t("onb1_d")}</p>
     <button class="opt ${state.lang === "en" ? "on" : ""}" data-olang="en"><strong>English</strong>&nbsp;· LTR</button>
     <button class="opt ${state.lang === "fa" ? "on" : ""}" data-olang="fa"><strong>فارسی</strong>&nbsp;· RTL</button>
     <div style="display:flex;gap:8px;margin-top:var(--sp-3)">
       <div class="theme-tile ${state.theme === "light" ? "on" : ""}" data-oth="light" style="background:#F8F8FA;color:#212129">${t("light")}</div>
       <div class="theme-tile ${state.theme === "dark" ? "on" : ""}" data-oth="dark" style="background:#141419;color:#ECECF1">${t("dark")}</div></div>`,
    `<h2>${t("onb2_t")}</h2><p class="lead">${t("onb2_d")}</p>
     <button class="opt on">🟢&nbsp;${t("onb_ollama")}</button>
     <button class="opt">🔑&nbsp;${t("onb_openai")}</button>
     <button class="opt">📴&nbsp;${t("onb_offline")}</button>`,
    `<h2>${t("onb3_t")}</h2><p class="lead">${t("onb3_d")}</p>
     <div class="set-row"><div class="lbl">${t("onb_net")}</div><div class="switch"></div></div>
     <div class="set-row"><div class="lbl">${t("onb_ask")}</div><div class="switch on"></div></div>
     <div class="set-row" style="border:none"><div class="lbl">${t("onb_where")}</div><span class="chip chip-plain ltr-island">~/.dream</span></div>`,
  ];
  d.innerHTML = `<div class="onb-card"><div class="card"><div class="onb-step">${steps[onbStep]}</div>
    <div class="dots">${[0, 1, 2].map((i) => `<i class="${i === onbStep ? "on" : ""}"></i>`).join("")}</div>
    <div class="acts">
      <button class="btn btn-ghost" id="onbBack">${onbStep ? t("back") : t("skip")}</button>
      <span class="spacer"></span>
      <button class="btn btn-primary" id="onbNext">${onbStep < 2 ? t("next") : t("finish")} ${onbStep < 2 ? "→" : "✓"}</button>
    </div></div></div>`;
  document.body.appendChild(d);
  $("#onbNext").addEventListener("click", () => { if (onbStep < 2) { onbStep++; renderOnb(); } else d.remove(); });
  $("#onbBack").addEventListener("click", () => { if (onbStep) { onbStep--; renderOnb(); } else d.remove(); });
  $$("[data-olang]", d).forEach((b) => b.addEventListener("click", () => {
    state.lang = b.dataset.olang;
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
    $$("#gLang button").forEach((x) => x.classList.toggle("on", x.dataset.v === state.lang));
    render(); applyStatic(); renderOnb();
  }));
  $$("[data-oth]", d).forEach((el) => el.addEventListener("click", () => {
    state.theme = el.dataset.oth; document.documentElement.dataset.theme = state.theme;
    $$("#gTheme button").forEach((x) => x.classList.toggle("on", x.dataset.v === state.theme));
    renderOnb();
  }));
  $$(".switch", d).forEach((s) => s.addEventListener("click", () => s.classList.toggle("on")));
}

/* ---------------- render ---------------- */
function render() {
  renderSidebar();
  ({ chat: viewChat, memory: viewMemory, subagents: viewSubagents,
     provenance: viewProvenance, data: viewData, settings: viewSettings }[state.view] || viewChat)();
}
applyStatic();
render();
