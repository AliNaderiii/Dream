# MASTER-P0 — گزارش پذیرش: مسیر اجرای کد (Code execution)

> این سند **دلایل واقعی** را ثبت می‌کند. هر عدد و هر خروجی از یک اجرای واقعی
> روی همین ماشین گرفته شده است. جاهایی که چیزی اثبات نشده، صریح نوشته شده.

---

## ۰. وضعیت نهایی — یک جمله

پیاده‌سازی مسیر نمای Code **کامل و سبز** است، اما **این کار تیک ۱۰ از ۱۰
نمی‌گیرد.** اجرای یک کانتینر واقعی در این محیط انجام شدنی نبود (نه `docker`،
نه دیمن)، پس **ایزوله‌سازی کانتینر در سطح تولید اثبات نشده است**. پس از دروازهٔ
تأیید، وضعیت درست این است: **۵ PASS، ۴ PARTIAL، ۱ BLOCKED، ۰ FAIL** — جدول
اصلاح‌شده در §۱۱، همراه با هشت یافته (F1–F8) و چهار تصمیم در انتظار کاربر
(D1–D4). هر ادعای «PASS» که به کانتینر زنده وابسته بود، به NOT VERIFIED تنزل
داده شد.

| | |
| --- | --- |
| شاخه | `arena/42128417-dream` |
| HEAD (ابتدا و انتها) | `7ac1a6d9bb144d9a1fc2ce70adbd98babfd37d58` |
| کامیت جدید | **هیچ** (طبق دستور، کامیت نزدم؛ همهٔ تغییرات در درخت کار است) |
| مسیرهای تغییریافته/جدید | ۳۱ (۲۴ تغییر یافته + ۷ فایل جدید) |
| Patch | `/home/user/p0-verification/MASTER-P0.patch` — ۳۱ فایل؛ تطابق دقیق با درخت کار با `git apply --check -R` (خروج ۰) تأیید شده. هش SHA-256 در فایل کنار آن، `MASTER-P0.patch.sha256`، ثبت شده است (خود این سند هم داخل پچ است، پس هش در سند نوشته نمی‌شود تا خودارجاعی پیش نیاید) |
| اسناد تأیید | `/home/user/p0-verification/MASTER-P0-VERIFICATION.md` (انگلیسی) |

---

## ۱. وضعیت مخزن در ابتدا و انتها

**ابتدا (baseline، پیش از هر ویرایش):**

- شاخهٔ `arena/42128417-dream`، HEAD `7ac1a6d9…`.
- تست کامل: `4079 passed, 16 skipped in 227.20s`
- تست دسکتاپ: `125 passed / 19 files`
- هیچ کامیت یا بازنویسی تاریخی انجام نشد؛ هیچ ابزار مخرب اجرا نشد.

**انتها:**

- همان شاخه، **همان HEAD**؛ ۳۰ مسیر در درخت کار (۲۴ تغییر یافته + ۶ فایل جدید).
- تست کامل: `4213 passed, 16 skipped in 227.98s` (یعنی **+134 تست** خالص).

---

## ۲. زنجیرهٔ فراخوانی فعال (اثبات‌شده، نه حدس)

```
[کلیک کاربر: «اجرا» در نمای Code]
  │
  ├─ apps/desktop/src/v5/shell/app.js:124        route 'code' → render: codeView
  ├─ apps/desktop/src/v5/views/code.js:257       api.sandboxRun(code)
  ├─ apps/desktop/src/v5/lib/bridge.js:384       call('sandbox.run_code',
  │                                                  {code, timeout_seconds},
  │                                                  {timeoutMs: 180_000})
  ├─ Tauri IPC:  invoke('bridge_send', {id, method, params})
  │     apps/desktop/src-tauri/src/bridge/mod.rs:238   bridge.send_request(...)
  │     ← لایهٔ Rust یک pass-through عمومی است؛ هیچ allowlist/فیلتر روشی ندارد
  ├─ JSON-RPC 2.0 روی stdin/stdout سایدکار پایتون
  ├─ Registry.dispatch → BridgeMethods.handlers['sandbox.run_code']
  │     dream/bridge/methods.py:729 → BridgeMethods.sandbox_run_code
  ├─ dream/security/codeexec.py
  │     CodeExecutionRequest.from_params()  ← اعتبارسنجی سمت بک‌اند
  │     CodeExecutionRuntime.run()          ← انتخاب اجراکننده + fail-closed
  ├─ dream/docker_sandbox.py  DockerSandbox.run_code(...)
  │     docker run --rm --name dream-code-* --network=none --cap-drop=ALL …
  └─ پاسخ: {status, execution_id, result{…}}  ← همان شکلی که code.js می‌خواند
```

**اثبات اینکه این زنجیره همان است که اجرا می‌شود:**

- `tests/test_code_execution_end_to_end.py` فرآیند واقعی
  `python -m dream.bridge` را اجرا می‌کند و روی لوله‌های واقعی حرف می‌زند؛
  هندلر ثبت‌شده را هم چاپ می‌کند:
  `dream.bridge.methods.BridgeMethods.sandbox_run_code`.
- `BridgeMethods.handlers` دارای **۳۸۹** متد است و `sandbox.run_code` در آن
  **فقط یک بار** تعریف شده است.
- `dream/bridge/methods_sandbox.py` عمداً هیچ `sandbox.run_code` ندارد (در
  docstring ماژول و در یک تست رگرسیون قفل شده است).

**مسیرهای مرده/قدیمی که دیگر فعال نیستند:**

| مسیر | وضعیت واقعی |
| --- | --- |
| `dream/sandbox/executor.py` (`SandboxExecutor`) | **غیرفعال مطلق.** مفسر میزبان حذف شده؛ `execute_python` مقدار `UNAVAILABLE` برمی‌گرداند. |
| `dream/sandbox/isolation/wasm_runtime.py` (`WasmMicroSandbox`) | **غیرفعال مطلق.** `available = False`، کد خروج ۱۲۶. هرگز WASM نبود و دیگر ادعا هم نمی‌کند. |
| `dream/sandbox/isolation/engine.py` (`IsolatedExecutionEngine`) | **غیرفعال.** هیچ تلمتری جعلی نمی‌سازد. |
| `dream/sandbox/isolation/seccomp_filter.py` | **فقط بازرسی ایستا.** سیس‌کال اجرا نمی‌کند؛ «فیلترِ هسته‌ای» نیست و دیگر این‌گونه توصیف نمی‌شود. |
| `sandbox_execute_python` (ابزار LLM) | در `dream.tools.base.REGISTRY` **هرگز نبوده** ⇒ مدل هرگز آن را نگرفته؛ حالا خودش هم `available: False` می‌دهد. |
| `/code` (اسلش) | هرگز به `cli.py` سیم‌کشی نشده بود؛ حالا وضعیت fail-closed را می‌گوید. |

---

## ۳. پنج نقش بازبینی: یافته‌ها و رفع اختلاف

**شفاف‌سازی الزامی:** در این محیط ابزار subagent وجود ندارد. بنابراین این پنج
نقش **پنج پاس بازبینی جداگانه** با لنزهای متفاوت بودند، نه پنج عامل مستقل.
«مستقل» در این گزارش یعنی «پاسِ دوم با لنز متفاوت»، نه «بازبینِ بیرونی». این
یک محدودیت واقعی است و به‌عنوان ریسک باقیمانده ثبت می‌شود.

### ۳.۱ مهندس Desktop/Tauri

- **یافته ۱:** نمای Code خروجی برنامه‌های **موفق** را نشان نمی‌داد. علت: بک‌اند
  یک شکل تخت `{stdout, stderr, return_code, …}` برمی‌گرداند، ولی `code.js`
  `response.result.stdout` را می‌خواند → چیپ خطای سرخ و **هیچ خروجی**.
- **یافته ۲:** لایهٔ Rust هیچ allowlist روشی ندارد (pass-through عمومی)، پس هیچ
  گیتی سمت Rust نبود که مسیر را ببندد؛ نقطهٔ خرابی صرفاً عدم تطابق شکل پاسخ بود.
- **تصمیم:** قرارداد **همان** قراردادی است که فرانت از قبل می‌خواند
  (`{status, execution_id, result}`)، بنابراین بک‌اند اصلاح شد نه UI بازنویسی.
  با این کار مسیر نمایش ترمیم شد، نه از نو اختراع.
- **اضافه شد:** چیپ وضعیت برای هر شش حالت (`success/error/timeout/cancelled/`
  `denied/unavailable`)، دکمهٔ لغو (`sandbox.cancel`)، خط «مشخصات ایزولاسیون»،
  و برچسب هشدار «بدون داکر اجرا نمی‌شود».
- **رفع اختلاف با نقش ۳ (امنیت):** امنیت می‌خواست timeout سمت کلاینت کوتاه‌تر
  باشد تا UI در انتظار نماند. مهندس Desktop مخالفت کرد چون کلاینتی که زودتر
  قطع کند یعنی **کانتینر بی‌صاحب می‌ماند**. تصمیم نهایی با شواهد کد: کلاینت
  ۱۸۰ ثانیه، سقف بک‌اند ۱۲۰ ثانیه — یعنی همیشه سمتی که می‌تواند کانتینر را
  بکشد اول شلیک می‌کند. این تصمیم در `bridge.js` کامنت شده است.

### ۳.۲ مهندس پل پایتون (Python bridge)

- **یافته:** `sandbox_run_code` به `CodeExecutionResponse` ارجاع می‌داد بدون
  ایمپورت کردنش ⇒ **هر رد درخواست** (code خالی، فیلد ممنوع، …) با `NameError`
  منفجر می‌شد، نه با پوشش `denied`. یعنی «مسیر fail-closed» در عمل خراب بود.
- **یافته:** `sandbox.run_code` **دو** تعریف داشت؛ تعریف extension
  (`methods_sandbox.py`) با یک مفسر میزبان `eval/exec` پشتش، و تعریف builtin با
  کانتینر. extension فقط چون `Registry.publish` متدهای هم‌نام را حذف می‌کند
  می‌باخت ⇒ سطح کد **یک تغییر در سیاست حل تعارض** با اجرای کد روی میزبان فاصله
  داشت. «دور از دسترس به‌طور تصادفی» یک کنترل نیست.
- **تصمیم:** حذف تعریف extension، نگه‌داشتن **یک** تعریف، و قفل کردن آن با تست.

### ۳.۳ مهندس امنیت کانتینر/سیستم‌عامل

- **یافتهٔ بحرانی:** `subprocess.CalledProcessError` با `stdout=` ساخته می‌شد،
  در حالی که امضای درست `(returncode, cmd, output=None, stderr=None)` است. نتیجه:
  **هر خروج غیرصفر داکر** یک `TypeError` می‌داد ⇒ برنامه‌ای که فقط `exit 1`
  داشت، به‌عنوان «خرابی داخلی اجراکننده» گزارش می‌شد و `stderr` آن دور ریخته
  می‌شد.
- **یافتهٔ پارامترهای گشادکنندهٔ مرز:** پارامترهای `env_vars`، `workspace_path`،
  `mount_workspace_read_write` و `network_enabled` می‌توانستند مرز را باز کنند.
  حالا **با نام رد می‌شوند** (`removed_field`) و فیلد ناشناخته `unknown_field`
  می‌گیرد — یعنی نمی‌توان با افزودن یک کلید، مرز را باز کرد.
- **یافتهٔ `--userns=remap`:** روی دیمن‌های استاندارد این فلگ `docker run` را
  کاملاً شکست می‌دهد. غیرشرطی کردنش یعنی تبدیل سخت‌سازی به قطعی سرویس؛ پس
  **opt-in** شد.
- **تأکید صریح:** پروفایل seccomp یک allow-list **گشاده** است و کنترل شبکه
  نیست؛ کنترل شبکه `--network=none` + `--cap-drop=ALL` است. این جمله در
  مستندات و در کد هست تا کسی seccomp را «سندباکس تضمینی» نخواند.

### ۳.۴ مهندس QA

- **یافته:** تست‌های قبلی صرفاً «هندلر را صدا می‌زدند». یک تست درون‌فرآیندی حتی
  وقتی متد ثبت‌شده اشتباه باشد سبز می‌ماند. پس یک تست **حمل‌ونقل واقعی** لازم
  بود: اجرای سایدکار واقعی روی لوله‌های واقعی.
- **یافتهٔ سبک:** دروازهٔ سبک سراسری مخزن
  (`tests/test_m16_conditional_assertions.py`) هر `assert` داخل `if` در توابع
  `test_*` را رد می‌کند. تست end-to-end من در اولین اجرا همین را شکست و اصلاح شد
  (assertها به یک هلپر ماژول‌سطحی منتقل شدند تا شرطِ خارج از کنترل تست، تست را
  ضعیف نکند).
- **سیاست:** اجراکنندهٔ جعلی مجاز است، اما **هرگز ادعای ایزولاسیون واقعی از آن
  استخراج نمی‌شود**. تست‌ها این تفکیک را در docstring خودشان می‌نویسند.

### ۳.۵ بازبین مستقل (شکار مسیرهای جایگزین و bypass)

- **یافته:** جاروب کل بستهٔ `dream/` با AST: **هیچ** فراخوانی سربرهٔ
  `eval()`/`exec()`/`compile()` باقی نمانده. (بررسی دوم روی `ast.Name` انجام شد،
  چون `re.compile` و `ast.literal_eval` فراخوانی روی attribute هستند و این
  الگو محسوب نمی‌شوند.) این جاروب حالا یک تست دائمی با تستِ خودِ آشکارساز است.
- **یافته:** `sandbox.list_backends` یک بک‌اند `local` را با توضیح
  «Local host shell ready» تبلیغ می‌کند. بررسی نشان داد این مربوط به
  `TerminalManager` (ترمینال `!shell`) است و **ربطی به `sandbox.run_code`
  ندارد** — یک تلهٔ نام‌گذاری، نه یک مسیر. در جدول ریسک‌ها ثبت شد.
- **یافته:** `workspace.shell_execute` فقط `approval_id` می‌گیرد (نه رشتهٔ
  فرمان) و سطحی جدا با کنترل‌های جداست.
- **یافته:** `DREAM_DATA_LOCAL_EXEC=1` برای مسیر research/dataQA یک اجرای
  زیرفرآیندی روی میزبان را ممکن می‌کند. این یک opt-in صریح است (نه fallback
  خودکار)، ولی **مرز امنیتی نیست** و نمای Code هم آن را نمی‌بیند. در
  مستندات و در جدول ریسک با همین صراحت آمده است.

---

## ۴. ریشه‌یابی، خلاصهٔ پیاده‌سازی و تصمیم‌های کلیدی

**ریشهٔ مشکل، دو شقه بود و هر دو لازم بود:**

1. **عدم تطابق قرارداد.** دو پیاده‌سازی هم‌نام با دو شکل پاسخ متفاوت، و برنده
   با «حذف تصادفی» تعیین می‌شد، نه با طراحی.
2. **ناامن‌بودن پیاده‌سازی بازنده.** همان پیاده‌سازی، مفسر **حالت‌دار روی
   میزبان** با یک بلاک‌لیست هفت‌regex بود.

**پیاده‌سازی:**

- `dream/security/codeexec.py` (جدید، ۱۱۵۵ خط) — تنها قرارداد تایپ‌شده:
  `CodeExecutionRequest` / `CodeExecutionResponse` / `CodeExecutionLimits` /
  `CodeExecutionStatus`، همهٔ کران‌ها، canonical‌سازی پوشهٔ کاری با بازکردن
  symlink زیر `DREAM_SANDBOX_ROOT`، و `CodeExecutionRuntime` که فقط و فقط به
  `DockerSandbox` واگذار می‌کند و در نبود آن **رد می‌کند**.
- `sandbox_run_code` بازنویسی شد تا فقط به این قرارداد واگذار کند؛
  `methods_sandbox.py` تعریف دوگانه‌اش را از دست داد.
- پاک‌سازی مسیر میزبان در `dream/sandbox/**` (executor، isolation، tools،
  slash، types) — همه fail-closed، بدون هیچ فراخوانی `eval`/`exec`/`compile`.
- `docker_sandbox.py` سخت شد: `--cap-drop=ALL`، `--security-opt=no-new-privileges`،
  `--read-only` + tmpfs محدود `/tmp`، کاربر غیرروت، `--network=none`، **دقیقاً
  یک bind mount**، `--memory-swap=0`، `--pids-limit`، `--cpus`، بدون هیچ متغیر
  محیطی میزبان (`-e` فقط HOME/TMPDIR/MPLCONFIGDIR/PYTHON*)، بدون سوکت داکر، و
  `docker rm -f` روی timeout و روی cancel.
- `DREAM_SANDBOX_IMAGE` تصویر پایتون را pin می‌کند (می‌توان digest داد). این
  override **فقط** برای زبان Python اعمال می‌شود تا اجرای R/Bash بی‌سروصدا به
  تصویر پایتون منحرف نشود.

**تصمیم‌های کلیدی (و چرایی):**

| تصمیم | چرا |
| --- | --- |
| قرارداد فرانت دست‌نخورده ماند و بک‌اند تطبیق داده شد | UI از قبل همان شکل را می‌خواند؛ تغییر آن یعنی دور ریختن مسیر نمایش سالم |
| `denied` **مقدار** است، نه استثنا | کلاینت یک شکل می‌بیند؛ استثنا در همهٔ مسیرهای UI دو شکل می‌سازد |
| params غیر-شیء یک `BridgeError` می‌ماند | آن قانون حمل‌ونقل است، نه رد برنامه |
| `variables_updated` همیشه `[]` | هر اجرا کانتینر تازه است؛ ادعای حالت‌داری دروغ می‌بود |
| `result.isolation` **همیشه** پر است | پروفایل امنیتی باید حتی در رد/عدم‌دسترسی دیده شود، وگرنه UI فقط در مسیر خوش‌بینانه آن را نشان می‌دهد |
| یک bind mount، هرگز home | کمترین mount اصل است، نه ضمیمه |
| `--userns=remap` فقط opt-in | روی دیمن استاندارد باعث قطع کامل می‌شود |
| کلاینت ۱۸۰s / بک‌اند ۱۲۰s | سمتی که کانتینر را می‌کشد باید اول تمام کند |

---

## ۵. فایل‌های تغییریافته

**جدید (۶):**

| فایل | خط | نقش |
| --- | --- | --- |
| `dream/security/codeexec.py` | ۱۱۵۵ | قرارداد تایپ‌شده + runtime |
| `tests/test_code_execution_contract.py` | ۷۱۰ | ماتریس قرارداد و تست‌های خصمانه (۶۲ تست) |
| `tests/test_docker_sandbox_hardening.py` | ۴۱۹ | اثبات argv واقعی `docker run` (۲۸ تست) |
| `tests/test_code_execution_end_to_end.py` | ۳۶۰ | سایدکار واقعی روی لولهٔ واقعی (۸ تست) |
| `tests/test_code_execution_route_containment.py` | ۳۵۴ | اثبات‌های عدم (۲۰ تست) |
| `docs/security/code-execution.md` | ۴۰۶ | مرجع: زنجیرهٔ فعال، قرارداد، fail-closed، ریسک‌ها، rollback |

**تغییر یافته (۲۴):**

`apps/desktop/src/v5/lib/bridge.js` (۲۵+)،
`apps/desktop/src/v5/views/code.js` (۱۵۹+)،
`apps/desktop/src/v5/views/code.test.js` (۲۶۳+، بازنویسی: ۱۶ تست)،
`docs/STATUS.md`، `docs/bridge/protocol.md` (§۳.۱۸ جدید)،
`docs/security/threat-model.md` (L9-A′)، `docs/handoff/P6.md`،
`docs/user/user-manual.md`،
`dream/bridge/methods.py`، `dream/bridge/methods_sandbox.py`،
`dream/docker_sandbox.py`، `dream/security/__init__.py`،
`dream/sandbox/{executor,slash,tools,types}.py`،
`dream/sandbox/isolation/{__init__,engine,slash,tools,wasm_runtime}.py`،
`tests/test_code_sandbox_and_interpreter.py` (بازنویسی: ۹ تست)،
`tests/test_desktop_sandbox_bridge.py` (بازنویسی: ۱۳ تست)،
`tests/test_sandbox_isolation_and_seccomp.py` (بازنویسی: ۱۳ تست).

---

## ۶. دستورها و **نتایج واقعی**

| دستور | نتیجهٔ واقعی |
| --- | --- |
| `/home/user/.venv/bin/python -m pytest -q -p no:cacheprovider` | **`4213 passed, 16 skipped in 227.98s`** |
| `… pytest tests/test_code_execution_contract.py tests/test_docker_sandbox_hardening.py tests/test_code_execution_route_containment.py tests/test_code_execution_end_to_end.py tests/test_desktop_sandbox_bridge.py tests/test_code_sandbox_and_interpreter.py tests/test_sandbox_isolation_and_seccomp.py tests/test_docker_sandbox.py tests/test_sec_agentic_sandbox.py -q` | **`227 passed in 17.08s`** |
| `/home/user/.venv/bin/ruff check .` | **`All checks passed!`** |
| `/home/user/.venv/bin/python tools/check_suite_count.py` | **`passed: 4218 tests collected (minimum required: 652)`** |
| `cd apps/desktop && npm test` | **`Test Files 19 passed (19) / Tests 138 passed (138)`** |
| `cd apps/desktop && npm run lint` | **خروجی خالی، کد ۰ (eslint پاک)** |
| `cd apps/desktop && npm run typecheck` | کد ۰ — **ولی این بررسی توخالی است:** `tsconfig.json` فقط `vite.config.ts` را include می‌کند، پس فایل‌های `.js` را typecheck نمی‌کند. این را ادعای پوشش تایپ حساب نکنید. |
| `cd apps/desktop && npm run build` | **`tsc --noEmit && vite build` موفق، `✓ 33 modules transformed`، خروجی `dist/`** (این یکی واقعاً importها و سینتکس JS را می‌بیند) |
| `npx prettier --check "src/**/*.{js,css}" "scripts/**/*.mjs"` | فایل‌های من پاک؛ فقط `src/v5/views/vision.js` هشدار دارد که **از قبل** همین‌طور بود و دست نزدم |
| `cd apps/desktop/src-tauri && cargo …` | **اجرا نشد** — روی این ماشین `cargo`/`rustc` وجود ندارد |
| `docker run …` | **اجرا نشد** — نه باینری داکر هست و نه دیمن |

**دو باگ واقعی که در همین کار پیدا و رفع شد (برای گزارش):**

1. `dream/bridge/methods.py` — `CodeExecutionResponse` ایمپورت نشده بود ⇒ هر رد
   درخواست `NameError` می‌داد به‌جای پوشش `denied`.
2. `dream/docker_sandbox.py` — `CalledProcessError(stdout=…)` به‌جای
   `output=` ⇒ هر خروج غیرصفر داکر `TypeError` می‌داد و کد خروج و `stderr`
   برنامه گم می‌شد.

---

## ۷. تست‌هایی که اجرا نشدند و **چرا**

| اجرا نشده | دلیل |
| --- | --- |
| اجرای یک کانتینر واقعی (شبکه، خواندن `/etc/shadow`، fork bomb، سیل خروجی) | روی این ماشین نه `docker` هست و نه دیمن — و **هیچ تستی هم برای این کار نوشته نشد**؛ فقط ادعاهای سطح `argv` نوشته شد. پس ادعای «کانتینر این کار را می‌کند» در هیچ‌جای این کار وجود ندارد؛ آن‌چه اثبات شده «دریم چه می‌خواهد» است، نه «هسته چه اعمال می‌کند». نوشتن این تست‌ها با `skipif` + یک job شبانه، باارزش‌ترین قدم بعدی است (بند ۱ ریسک‌ها). |
| `cargo fmt / clippy / build / test` در `apps/desktop/src-tauri` | زنجیرهٔ ابزار Rust نصب نیست. لایهٔ Rust دست‌نخورده است (pass-through عمومی) و تغییری در آن نداشتم. |
| `npm run tokens:check` / `performance:check` / `accessibility:check` | بخشی از `npm test` نبودند و به این تغییر ربطی ندارند؛ اجرا نشدند. |
| `ruff format --check .` | در CI استفاده نمی‌شود و مخزن از قبل format-clean نیست (۳۵۹ فایل). دروازهٔ CI فقط `ruff check .` است که سبز است. |

---

## ۸. چک‌لیست پذیرش ۱–۱۰

| # | معیار | وضعیت | شواهد |
| --- | --- | --- | --- |
| ۱ | درخواست نمای Code در حال استفاده به هندلر موردنظر و اجراکنندهٔ ایزوله از طریق registration/dispatch واقعی می‌رسد | **PASS (dispatch) / NOT VERIFIED (اجرای داخل کانتینر)** | مسیر کامل در §۲؛ `handlers['sandbox.run_code']` دقیقاً یک بار → `dream.bridge.methods.BridgeMethods.sandbox_run_code` (اثبات‌شده با اجرای سایدکار واقعی)؛ `app.js:124` مسیر `code` را به `codeView` می‌بندد. **دامنهٔ اثبات:** رسیدن به هندلر + انتخاب اجراکننده؛ رسیدن فیزیکی به یک کانتینر روی این ماشین اثبات‌نشدنی است (بند ۳). |
| ۲ | قرارداد تایپ‌شدهٔ واحد، هم‌خوان بین فرانت و بک‌اند، با اعتبارسنجی | **PASS** | ۶۲ تست قرارداد + ۱۶ تست vitest + تست شکل‌دقیقِ سیم در e2e؛ فرانت فقط `code` و `timeout_seconds` می‌فرستد (تست روی سورس بدون mock) |
| ۳ | هیچ کد تولیدشدهٔ مدل به مسیر اجرای میزبان/قدیمی نمی‌رسد | **PASS** | جاروب AST کل `dream/`: صفر فراخوانی سربرهٔ `eval/exec/compile`؛ رجیستری ابزار مدل هیچ ابزار اجرای میزبان ندارد؛ `tool.execute` رد می‌کند؛ ۲۰ تست containment. **استثنای قبلی حالا بسته شد:** با تصمیم D1، هم `DREAM_DATA_LOCAL_EXEC=1` و هم fallback خودکارِ خطای import حذف شدند؛ تنها اجراکنندهٔ محلی باقی‌مانده یک fixture تستی زیر `tests/` است که هیچ ماژول محصولی آن را import نمی‌کند (اثبات در `tests/test_no_local_execution_fallback.py`) |
| ۴ | نبود/خرابی ایزولاسیون ⇒ پاسخ دیده‌شدنی fail-closed، بدون fallback خودکار به میزبان | **PASS** | تست e2e روی ماشینی بدون داکر: `status="unavailable"`، `stdout=""`، `exit_code=-1`، کد خطای `docker_unavailable`، و پیام دوزبانه‌ای که صریح می‌گوید روی میزبان اجرا نمی‌شود |
| ۵ | فایل‌سیستم محدود به پوشهٔ کاری مجاز؛ تست‌های traversal و symlink سبز | **PASS (جلوگیری از فرار) / NOT VERIFIED (جداسازی بین اجراها)** | مسیر مطلق بیرون، `..`، symlink، پوشهٔ والد symlink‌شده، مسیر آرتیفکت، و `reset` که نباید از لینک بیرون برود — همه در ماتریس قرارداد |
| ۶ | محدودیت‌های زمان اجرا/خروجی/لغو توسط **بک‌اند** اعمال می‌شود | **BLOCKED — تأییدنشده** | ۲۸ تست argv: `--network=none`، `--read-only`، `--memory-swap=0`، `--pids-limit`، `--cpus`، سقف خروجی، `docker rm -f` روی timeout و روی cancel. **اثبات فقط در سطح API/argv است و همین کافی نیست:** محدودیت‌های اعمال‌شده توسط هسته، لغو واقعی، و نابودسازی واقعی درخت فرایند همه به کانتینر زنده نیاز دارند. یک تست argv اثبات یک مرز زنده نیست ⇒ BLOCKED |
| ۷ | هیچ رازی و هیچ mount نامحدودی به فرایند کد داده نمی‌شود | **PARTIAL** | دقیقاً یک bind mount؛ `-e`ها فقط HOME/TMPDIR/MPLCONFIGDIR/PYTHON*؛ سوکت داکر mount نمی‌شود؛ `env_vars` با نام رد می‌شود. **اما اعتماد تصویر اعمال نمی‌شود:** `DREAM_SANDBOX_IMAGE` بدون هیچ اعتبارسنجی و بدون الزام digest پذیرفته می‌شود (یافتهٔ F2)، و «آن‌چه کانتینر واقعاً می‌بیند» بدون کانتینر تأییدنشده است |
| ۸ | تست‌های متمرکز سبز + تست‌های گستردهٔ مرتبط اجرا شده | **PASS** | `4213 passed, 16 skipped`؛ `ruff All checks passed`؛ دسکتاپ `138 passed`؛ `npm run build` موفق |
| ۹ | مستندات با پیاده‌سازی می‌خوانند و محدودیت‌ها را می‌گویند | **PASS** | `docs/security/code-execution.md` (جدید)، `protocol.md §3.18`، `threat-model.md L9-A′`، `user-manual.md §7`، `STATUS.md`، `P6.md`؛ همهٔ لینک‌های md بازبینی و معتبرند |
| ۱۰ | بازبینی مستقل مسیرهای جایگزین و bypass را جسته است | **PASS** | ۲۰ تست containment + جدول کامل مسیرها در §۱۱ (۱۶ مسیر فعال) + یافته‌های F1–F8. **محدودیت:** «مستقل» = پاس دوم با لنز متفاوت؛ ابزار subagent وجود ندارد. جاروب AST صرفاً یک پین رگرسیون است، نه اثبات نبود مسیر ناامن |

**جدول بالا اصلاح‌شده است.** نسخهٔ اول این گزارش ۱۰ از ۱۰ PASS نوشته بود که
برای معیارهای وابسته به کانتینر زنده نادرست بود. وضعیت نهایی: **۵ PASS
(۲، ۳، ۴، ۸، ۹)، ۴ PARTIAL (۱، ۵، ۷، ۱۰)، ۱ BLOCKED (۶)، ۰ FAIL.**

**ایزوله‌سازی کانتینر در سطح تولید تأیید نشده است.** هیچ کانتینری در این محیط
اجرا نشد؛ تنها شواهد موجود، ساخت argv و کنترل‌های سطح API هستند.

---

## ۹. ریسک‌های باقیمانده، محدودیت‌ها، مهاجرت و بازگشت

### ریسک‌های باقیمانده (به ترتیب اهمیت)

1. **هیچ تست یکپارچگی با کانتینر واقعی در CI نیست** (بدون دیمن). باارزش‌ترین
   قدم بعدی: یک job شبانه با داکر که یک payload کاناری بفرستد (تلاش شبکه،
   خواندن `/etc/shadow`، نوشتن در `~`، fork bomb، سیل خروجی) و رد شدن هر یک را
   ثابت کند، به‌همراه تستی که مطمئن شود کانتینر پس از timeout رفته است.
2. **فرار از Docker/هسته** خارج از کنترل دریم است (پذیرفته‌شده).
3. **`--userns=remap` پیش‌فرض خاموش است** (چون روی دیمن استاندارد شکست می‌خورد).
4. **پروفایل seccomp گشاده است** و کنترل شبکه محسوب نمی‌شود.
5. **تصویر با tag کشیده می‌شود، نه digest** — برای مدل تهدید سخت‌گیرانه
   `DREAM_SANDBOX_IMAGE` را با digest تنظیم کنید.
6. **`sandbox.analyze_data` با آرگومان مسیر** یک سطح خواندن داده روی میزبان است
   (با `is_sensitive_path` محافظت‌شده)؛ محدودکردن به ریشهٔ سندباکس یک سخت‌سازی
   معقول آینده است.
7. **بدون سقف زمان CPU** (فقط `--cpus` به‌عنوان نرخ + ساعت دیواری).
8. **`DREAM_DATA_LOCAL_EXEC`** یک opt-in اجرای میزبان برای research/dataQA
   باقی می‌ماند (§۳.۵).
9. **«مستقل» در بازبینی معنی کامل کلمه را نمی‌دهد** — ابزار subagent نبود.
10. **مسیرهای جایگزین مستندشده ولی خارج از دامنه:** `notebook_execute` /
    `notebook_run_cell`، `sandbox.install_packages`، `sandbox.run_notebook`،
    `mcp.call_tool`، `browser.execute_js`، `shell=True` در
    `dream/tools/system_tools.py`. در §۸ مستند مرجع فهرست شده‌اند تا ادعای
    «همه‌جا بسته شد» نشود.

### محدودیت‌های پلتفرم

| پلتفرم | وضعیت |
| --- | --- |
| Linux | پشتیبانی‌شده. Docker Engine ≥ 20.10 با دیمن قابل دسترس. |
| macOS | پشتیبانی‌شده (Docker Desktop / Colima). `--user` به پیش‌فرض تصویر واگذار می‌شود چون نگاشت id را VM کانتینر دارد؛ و این در `result.isolation.user` **صادقانه گزارش** می‌شود، نه ادعا. |
| Windows | پشتیبانی‌شده با بک‌اند WSL2. `os.getuid` وجود ندارد ⇒ `--user` پیش‌فرض تصویر، باز هم گزارش‌شده. |

**پیش‌نیاز اجباری: دیمن داکر.** بدون آن، نمای Code «در دسترس نیست» می‌دهد و
**هیچ چیز روی ماشین اجرا نمی‌شود**. دریم برای سرپا نگه‌داشتن دکمه، کد را محلی
اجرا نمی‌کند.

### یادداشت مهاجرت

- **هیچ مهاجرت داده‌ای لازم نیست.** تاریخچهٔ اجرا در حافظه است و پوشه‌های
  اجرای هر run زیر `DREAM_SANDBOX_ROOT` (`~/.dream/sandbox`) قرار دارند و
  حذفشان بی‌خطر است.
- اگر کسی قبلاً `sandbox.run_code` را از سمت extension صدا می‌زد، شکل پاسخ عوض
  شده است: `{status, result{…}}` با شش مقدار مجاز برای `status`. هر مصرف‌کنندهٔ
  بیرونی باید به این قرارداد مهاجرت کند.

### دستور بازگشت (rollback)

مجموعهٔ تغییرات MASTER-P0 را برگردانید. **دو نیمه باید با هم برگردند**، وگرنه
نمای Code چیزی نشان نمی‌دهد:

- بک‌اند: `dream/security/codeexec.py`، `dream/bridge/methods.py::sandbox_run_code`،
  `dream/bridge/methods_sandbox.py`، `dream/docker_sandbox.py`،
- فرانت: `apps/desktop/src/v5/views/code.js`، `apps/desktop/src/v5/lib/bridge.js`.

برگرداندن فقط بک‌اند، همان پاسخ تخت `{stdout, stderr, return_code, …}` را
برمی‌گرداند که `code.js` نمی‌تواند بخواند. برگرداندن فقط فرانت، دیدی را
برمی‌گرداند که `result.result.stdout` می‌خواند در حالی که بک‌اند شکل تخت
می‌دهد. هیچ‌کدام تنها معنا ندارند.

---

## ۱۰. صداقت گزارش

- هیچ خروجی تستی ساخته یا بازنویسی نشده؛ همهٔ اعداد از اجرای واقعی روی همین
  ماشین است.
- هیچ تضمین امنیتی از یک اجراکنندهٔ جعلی استخراج نشده است.
- جاهایی که اثبات نشده (کانتینر واقعی، Rust، توخالی‌بودن `typecheck`) صریح
  علامت خورده است.
- مرز امنیتی برای «سبز شدن UI» ضعیف نشد؛ در نبود ایزولاسیون، پاسخ
  `unavailable` است.

---

## ۱۱. دروازهٔ تأیید — مسیرهای اجرا، اعتماد تصویر/پوشهٔ کاری، و یافته‌های باز

این بخش پاسخ دروازهٔ تأیید است. هیچ کد و هیچ تستی در جریان آن تغییر نکرد.

### ۱۱.۱ فهرست کامل مسیرهای اجرا

روش: جدول dispatch در زمان اجرا شمرده شد (**۳۸۹** متد؛ فهرست کامل در
`/home/user/p0-verification/handler-inventory.txt`)، سپس هر نامزد دستی در
سورس دنبال شد. جاروب AST فقط یک بررسی مکمل است، **نه اثبات** — چون مسیرهای
۵، ۸، ۹، ۱۰ و ۱۶ هیچ `eval` سربره‌ای ندارند و با این حال کد اجرا می‌کنند.

| # | نقطهٔ ورود | می‌تواند کد مدل را اجرا کند؟ | کجا اجرا می‌شود | تأیید/پیکربندی لازم | وضعیت | تست | ریسک باقی‌مانده |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ۱ | **نمای Code**: `sandbox.run_code` → Tauri `bridge_send` → `BridgeMethods.sandbox_run_code` → `CodeExecutionRuntime.run` → `DockerSandbox.run_code` | بله | فقط کانتینر؛ در غیر این صورت `unavailable` | ندارد | **فعال** | ۵ فایل تست + `code.test.js` | رفتار کانتینر اینجا تأییدنشده |
| ۲ | **research / dataqa** → `CodeActExecutor.run` → `SandboxCodeExecutor` (دروازهٔ AST + کانتینر) | بله (اسنیپت مدل، فیلترشده) | **فقط کانتینر** (D1)؛ در نبود آن `ContainerUnavailableError` و `FAILED` | ندارد؛ متغیر محیطی حذف شده و بی‌اثر است | فعال | `test_no_local_execution_fallback.py` (۱۹ تست) + `test_research_security.py` (با نبود pandas skip شد) | F4 **بسته شد**؛ مسیر محلی وجود ندارد |
| ۳ | **pipeline داده** (`sandbox.analyze_data`، پاک‌سازی/نمودار/گزارش) | اسکریپت تولیدی دریم با پارامترهای مدل | **فقط کانتینر**؛ در نبود آن `ExecResult(available=False, 126)` | ندارد | فعال | `test_no_local_execution_fallback.py`، `test_data_science*` | F4 **بسته شد** |
| ۴ | **`DREAM_DATA_LOCAL_EXEC=1`** → `LocalPythonExecutor.run` | — | — | — | **حذف شد (D1)** | `test_no_local_execution_fallback.py` | کلاس از محصول پاک شد؛ متغیر محیطی بی‌اثر است؛ تنها بازمانده یک fixture تستی زیر `tests/` است |
| ۵ | **Notebook/Jupyter** (`notebook.*`) → `jupyter_client.KernelManager.start_kernel` | بله (هر سلولی که نوشته شده) | **هستهٔ Jupyter روی میزبان** | نصب jupyter_client؛ مسیر داخل ریشهٔ دیتاست‌ها | فعال (اینجا skip) | `test_notebooks_kernel.py` (skip) | هستهٔ میزبان با دسترسی فایل‌سیستم و محیط دریم — **بدون سندباکس** |
| ۶ | **`sandbox.run_notebook`** → mount پوشهٔ والد نوت‌بوک + `nbconvert --execute` | بله | کانتینر، اما با mount پوشهٔ دلخواه میزبان | ندارد؛ مسیر آزاد است | فعال | تست اختصاصی ندارد | **F3** |
| ۷ | **`sandbox.install_packages`** → Dockerfile + `docker build` | نام بسته‌های ورودی داخل خط `RUN` درج می‌شود | build کانتینر (شبکه روشن، root) | ندارد | فعال | تست اختصاصی ندارد | **F5** — تزریق فرمان در build |
| ۸ | **MCP stdio** (`mcp.add_server` + اتصال) → `create_subprocess_exec(cmd, *args)` | غیرمستقیم و کامل | **میزبان** | فقط دسترسی به bridge | فعال | `tests/security/test_sec_mcp_hygiene.py` | **F6** — بدون دروازهٔ تأیید و بدون allowlist |
| ۹ | **`!shell`** (`workspace.shell_propose`/`shell_execute`) → `ShellGate` | بله (متن فرمان) | **میزبان** (`shell=False`، مسیر محصور، env ثابت) | دو مرحله‌ای: propose سپس `approval_id`؛ `dangerous` هرگز اجرا نمی‌شود | فعال | `test_code_execution_route_containment.py` | طبقه‌بند heuristic فقط |
| ۱۰ | **ابزار مدل `run_shell`** (`tool.execute`، `risk=dangerous`) → `subprocess.run(shell=True)` | بله | **پوستهٔ میزبان** | تأیید انسانی الزامی + L3 floor | فعال | تست‌های approval/floor | `shell=True` با متن مدل؛ تنها کنترل، تأیید است |
| ۱۱ | **بک‌اندهای ترمینال** (`sandbox.list_backends`/`set_backend`) | `TerminalManager.execute` می‌تواند — اما **هیچ متد bridge آن را صدا نمی‌زند** | میزبان/کانتینر/دور | — | فعال ولی برای اجرا **دسترس‌ناپذیر** | `test_code_execution_route_containment.py` | افزودن یک handler آینده آن را باز می‌کند |
| ۱۲ | **`browser.execute_js`** → Playwright `evaluate` | بله (JS) | داخل صفحهٔ مرورگر میزبان | `_require_browser`؛ بدون دروازهٔ تأیید | فعال | تست‌های مرورگر | دسترسی کامل درون نشست صفحه |
| ۱۳ | **ACP client** (`acp.client.*`) | خیر (فقط ارسال prompt) | **دور** (HTTP) | پیکربندی | فعال | تست‌های acp | خروج داده؛ SSRF-گونه؛ اجرای کد محلی ندارد |
| ۱۴ | **افزونه‌ها** (`dream/plugins/`) | کد افزونه در همان فرایند | **فرایند دریم (میزبان)** | نصب/فعال‌سازی افزونه | فعال | تست‌های plugin | کد افزونه ذاتاً مورد اعتماد است |
| ۱۵ | **مسیرهای بازنشسته**: `sandbox/executor.py`، `sandbox/isolation/*`، ابزار `sandbox_execute_python`، `/code` | خیر — همه رد می‌کنند و `unavailable` می‌دهند (کد خروج ۱۲۶) | — | — | **غیرفعال** | `test_code_execution_route_containment.py` و دو فایل دیگر | فقط بازرس ایستا باقی مانده |
| ۱۶ | **`dream/dataqa/executor.py`** (کارگر plan-محور) | **خیر** — `worker.py` پلن را به‌عنوان داده تفسیر می‌کند (شاخه روی `plan["action"]`، بدون `eval`/`query`/`expr`) | **میزبان** با rlimits (CPU 8s، AS 512MB، NOFILE 32، NPROC 1) و مهلت ≤ ۳۰s | ندارد | فعال | `test_dataqa_security.py` | فرایند میزبان، اما سطح کد دلخواه نیست |

بررسی‌شده و **مسیر اجرا نیستند**: `router/semantic.py::_predict_tools` (فهرست
نام)، `tool.list`، `sandbox.cancel/reset/get_status/status/list_artifacts`،
`space.*`، `evals.*`، `swarm.*`، `council.run`، `subagent.spawn`، `gateway.*`
(دروازهٔ وب فقط REST مدیریتی و SPA را سرو می‌کند — هیچ proxying عمومی RPC
ندارد)، `system.*`، `duplex.*`، `skills.*`.

### ۱۱.۲ DREAM_SANDBOX_IMAGE — اعتبارسنجی و انتخاب

`DockerSandbox._image_for(Language.PYTHON)` مقدار
`DREAM_SANDBOX_IMAGE` را **بدون هیچ اعتبارسنجی** و بی‌کم‌وکاست برمی‌گرداند؛
فقط زبان Python قابل override است. شواهد اجراشده:

```
env=''                                 -> 'python:3.12-slim'
env='evil/anything:latest'             -> 'evil/anything:latest'
env='registry.example/x@sha256:aaaa…'  -> همان مقدار
```

پاسخ صریح: **پیکربندی می‌تواند به یک تصویر دلخواه و mutable اشاره کند.** به
فهرست تأییدشده محدود نیست و digest الزامی نیست. این ورودی *از قرارداد Code*
نمی‌آید (قرارداد فیلد `image` را رد می‌کند)؛ پس اپراتوری است که محیط را کنترل
می‌کند — و همان اپراتور می‌تواند دیمن را هم عوض کند. طبقه‌بندی صادقانه:
**تحت کنترل اپراتور، بدون اعتبارسنجی، بدون pin digest** (F2). در این کار هیچ
تصویر نامعتبری pull یا اجرا نشد.

### ۱۱.۳ پوشهٔ کاری: آیا فراخوان می‌تواند پوشهٔ اجرای دیگری یا مسیر دلخواه میزبان را انتخاب کند؟

شواهد اجراشده (`/home/user/p0-verification/workspace-and-image-evidence.txt`):

| درخواست | نتیجه |
| --- | --- |
| `/tmp/outside-…` (بیرون ریشه) | **DENIED** `workspace_outside_root` |
| `/etc` | **DENIED** `workspace_outside_root` |
| symlink از داخل ریشه به بیرون | **DENIED** `workspace_outside_root` |
| `<root>/runs/some-other-execution` | **ACCEPTED** |
| `<root>` (خود ریشهٔ سندباکس) | **ACCEPTED** |
| `execution_id="../../etc"` | **DENIED** `invalid_execution_id` |
| `execution_id=".."` → `workspace_for` | **خود ریشهٔ سندباکس** |

یعنی:

- **mount مسیر دلخواه میزبان از راه `sandbox.run_code` ممکن نیست**: پوشهٔ کاری
  با بازکردن symlink canonicalize می‌شود، باید از قبل به‌صورت پوشه وجود داشته
  باشد، باید داخل `DREAM_SANDBOX_ROOT` بماند و بعد از `mkdir` دوباره بررسی
  می‌شود. دقیقاً یک bind mount ساخته می‌شود.
- **جداسازی بین اجراها وجود ندارد.** چون `_EXECUTION_ID_RE` نقطه را می‌پذیرد،
  `execution_id=".."` (یا `"."`/`"runs"`) پوشهٔ کاری را به خود ریشه یا `runs/`
  می‌برد، و `workspace` صریح می‌تواند **هر** پوشهٔ داخل ریشه — از جمله پوشهٔ
  اجرای دیگر — را نام ببرد. همهٔ اجراها متعلق به یک کاربر OS در یک اپ
  تک‌کاربره‌اند، پس این «محصور بودن به ریشه» است، نه مرز امتیاز. یک اجرا
  می‌تواند فایل‌های اجرای دیگر را بخواند/بنویسد. یافتهٔ **F1**.

**مسیرهایی که واقعاً mount میزبان با انتخاب فراخوان انجام می‌دهند** (بیرون از
قرارداد Code، رفع‌نشده): `sandbox.run_notebook` (پوشهٔ والد نوت‌بوک — F3) و در
مسیرهای داده، پوشهٔ دیتاست (که از یک دیتاست ثبت‌شده می‌آید، نه از مسیر خام).

### ۱۱.۴ reset، artifacts، پاک‌سازی و symlink

`reset()` فقط فرزندان `root/runs` را پیمایش می‌کند، هر چیزی که `resolve()` آن
بیرون ریشه باشد یا خود ریشه باشد را رد می‌کند، symlink را دنبال نمی‌کند، و فقط
همان‌ها را `rmtree` می‌کند. `_artifacts_for()` فقط پوشهٔ کاری همان اجرا را
می‌پیماید، symlink و هر مسیری که از ریشه بیرون بزند را رد می‌کند و تنها
فایل‌های معمولی را ثبت می‌کند؛ `list_artifacts()` هیچ دسترسی فایل‌سیستمی
انجام نمی‌دهد. «کاربر دیگر» وجود ندارد: ریشه به‌ازای هر کاربر OS است و دروازهٔ
وب هیچ RPC پلی‌ای را expose نمی‌کند؛ «نشست دیگر» همان مورد F1 است.

**کدام ادعا unit-tested است و کدام به داکر واقعی نیاز دارد:** محصور بودن پوشهٔ
کاری، symlink، `/etc`، بیرون ریشه، رفتار `reset` و شمردن artifacts → **تست
واحد دارند**. یک mount، read-only، `--network=none`، نبود سوکت، نبود env میزبان
→ **فقط argv**. اینکه کانتینر واقعاً شبکه ندارد / نمی‌تواند `/etc/shadow`
بخواند / بیرون mount نمی‌نویسد / بعد از cancel واقعاً رفته → **نیازمند تست
یکپارچگی داکر واقعی، اجرانشده**.

### ۱۱.۵ یافته‌های باز (بدون هیچ تغییر کد)

| شناسه | یافته | شدت |
| --- | --- | --- |
| **F1** | اجراها فقط تا ریشهٔ سندباکس محصورند؛ `execution_id=".."` یا `workspace` صریح می‌تواند پوشهٔ اجرای دیگر/ریشه/`runs` را انتخاب کند | متوسط |
| **F2** | `DREAM_SANDBOX_IMAGE` بدون اعتبارسنجی و بدون الزام digest استفاده می‌شود | متوسط |
| **F3** | `sandbox.run_notebook` مسیر دلخواه میزبان می‌گیرد و پوشهٔ والد آن را mount می‌کند؛ نام فایل داخل خط فرمان پوسته درج می‌شود | متوسط‑بالا |
| ~~**F4**~~ | **بسته شد با تصمیم D1:** مسیر محلی و fallback خطای import حذف شدند؛ `docker_available()` حالا وضعیت واقعی اجراکننده را می‌گوید و `run.start` هم `sandbox_available` را می‌فرستد | — |
| **F5** | `sandbox.install_packages` نام بسته‌ها را داخل خط `RUN` درج می‌کند ⇒ تزریق فرمان در build (شبکه روشن، root) | متوسط‑بالا |
| **F6** | `mcp.add_server` + اتصال، هر باینری دلخواه را روی **میزبان** بدون دروازهٔ تأیید اجرا می‌کند | بالا |
| **F7** | یک fixture تست، توکن کامل‌شکل `ghp_…` را به‌صورت literal دارد؛ خلاف قرارداد مخزن (ساخت از قطعه‌ها) که روبات اسکنر راز نمی‌بیند | پایین |
| **F8** | هیچ تست یکپارچگی با کانتینر زنده وجود ندارد (و `skipif`-guarded هم نوشته نشد) | بالا (شکاف تأیید) |

### ۱۱.۶ تصمیم‌های در انتظار کاربر

- **D1 — ✅ تصمیم گرفته شد و پیاده شد: گزینهٔ (ج).** کاربر دستور داد مسیرهای
  research/data-QA فقط کانتینری شوند و هم متغیر محیطی و هم fallback خطای import
  حذف شوند. جزئیات پیاده‌سازی و شواهد در §۱۲.
- **D2 — دامنهٔ F1/F3/F5/F6:** در همین کار رفع شوند (بیرون از دامنهٔ اصلی نمای
  Code هستند)، به‌عنوان کار بعدی ثبت شوند، یا به‌عنوان ریسک مستند بمانند؟
- **D3 — F2 و F8:** الزام digest برای `DREAM_SANDBOX_IMAGE` (با راه فرار)؟ و
  آیا مجموعهٔ تست کانتینر زنده همین حالا نوشته شود (اینجا اجراشدنی نیست)؟
- **D4 — F7:** تأیید بازنویسی یک‌خطی fixture به سبک قطعه‌ای.

### ۱۱.۷ بازبینی تغییر تست‌ها (خلاصه)

هر سه فایل بازنویسی‌شده **هدف فایل** را حفظ کرده‌اند؛ حذف‌شده‌ها assertions
دربارهٔ *اجرای روی میزبان* بودند، یعنی همان رفتاری که این کار حذف کرد.
**هیچ تستی حذف نشد و هیچ assertی برای سبز شدن حذف/ضعیف نشد** — دروازهٔ سبک
سراسری مخزن (`tests/test_m16_conditional_assertions.py`) خودِ
`assert` داخل `if` را در همهٔ `tests/*.py` رد می‌کند و یکی از تست‌های جدید من
هم به همین دلیل به helper منتقل شد (assertها شرطی نشدند، فقط جابه‌جا شدند).
یک ادعای نادرست: `npm run typecheck` برای فایل‌های تغییریافته **بی‌اثر** است،
چون `tsconfig.json` فقط `vite.config.ts` را include می‌کند؛ بررسی واقعی
`npm run build` بود.

### ۱۱.۸ صداقت این دروازه

- هیچ کد یا تستی در جریان این دروازه تغییر نکرد. تنها سندها به‌روز شدند.
- پچ کامل در `/home/user/p0-verification/MASTER-P0.patch` است و با
  `git apply --check -R` (خروج ۰) تطابق دقیق آن با درخت کار تأیید شد.
- **ایزوله‌سازی کانتینر در سطح تولید تأیید نشده است.** ادعاهای کانتینری این
  گزارش در سطح «دریم چه می‌خواهد» هستند، نه «هسته چه اعمال می‌کند».
- در این نوبت، `pytest`/`ruff`/`npm` دوباره اجرا نشدند چون `/home/user/.venv` و
  `apps/desktop/node_modules` در snapshot این نوبت وجود ندارند؛ اعداد تست از
  اجراهای ثبت‌شدهٔ همین کار نقل شده‌اند و به‌عنوان «نقل‌شده» علامت خورده‌اند.

---

## ۱۲. اجرای تصمیم D1 — حذف کامل مسیر اجرای محلی (بدون fallback)

**دستور کاربر:** حذف کامل مسیر `DREAM_DATA_LOCAL_EXEC=1` و حذف fallback خودکارِ
خطای `ImportError`؛ فقط کانتینر، و در نبود آن یک نتیجهٔ تایپ‌شدهٔ `unavailable`.
هیچ‌چیز محلی نباید به‌عنوان سندباکس توصیف شود، و اگر ابزار توسعه‌دهنده لازم است
باید بیرون از مسیر عامل، فقط توسعه‌ای، و از UI/ابزار مدل/RPC دور باشد.

### ۱۲.۱ چه چیزی حذف/تغییر کرد

| فایل | تغییر |
| --- | --- |
| `dream/skills/data_science.py` | کلاس `LocalPythonExecutor` **حذف شد**؛ `UnavailableCodeExecutor` جایش را گرفت (هیچ‌وقت و در هیچ پلتفرمی اجرا نمی‌کند). `_default_executor()` حالا فقط `SandboxCodeExecutor(DockerSandbox())` می‌دهد یا این stub. `ExecResult` سه فیلد صادقانه گرفت: `available`, `error_code`, و پراپرتی `unavailable`. `SandboxCodeExecutor` خطاهای «کانتینر حتی شروع نشد» (`DockerUnavailableError`, `SandboxExecutionError`, `OSError` که نبودِ باینری docker را پوشش می‌دهد) را به همان نتیجهٔ تایپ‌شده تبدیل می‌کند. `subprocess` و `sys` از importهای ماژول **حذف شدند** ⇒ این فایل هیچ نقطهٔ ورود spawn ندارد. |
| `dream/skills/data_science.py` | `DataScienceUnavailableError(DataScienceError)` اضافه شد؛ `_run` پیش از هر چیزِ دیگری آن را raise می‌کند (نه پیام مبهم «sandbox execution failed»). |
| `dream/research/executor.py` | `ContainerUnavailableError(ResearchError)` اضافه شد؛ `run()` **پیش از هر نوشتن روی دیسک** `require_backend()` را صدا می‌زند. `_warn_if_local`/`_warned_local` حذف شدند. `docker_available(runtime)` حالا وضعیت واقعی اجراکننده را می‌گوید (قبلاً فقط import بودن ماژول را چک می‌کرد و روی ماشین بدون دیمن `True` می‌داد). `backend`/`backend_available` از خود اجراکننده خوانده می‌شوند. |
| `dream/research/session.py` | گزارش `run.start` حالا `sandbox=<backend واقعی>` و `sandbox_available=<bool>` است؛ رشتهٔ `"local-subprocess"` دیگر ممکن نیست. شاخهٔ صریح `except ContainerUnavailableError` **پیش از** `except Exception` اضافه شد ⇒ `FAILED` با پیام روشن. |
| `dream/bridge/errors.py` | `UNAVAILABLE = -32010` رسماً به تاکسونومی اضافه شد (قبلاً یک عدد جادویی پراکنده در `_require_sandbox` بود). |
| `dream/bridge/methods.py` | `_data_call` حالا `DataScienceUnavailableError` را به `UNAVAILABLE` با `data={"code","status":"unavailable"}` نگاشت می‌کند، نه به `INVALID_PARAMS`. `_require_sandbox` هم از نماد استفاده می‌کند. |
| `tests/_data_science_helpers.py` | `LocalTestExecutor` — **fixture تستی**، صریحاً نه سندباکس؛ فقط زیر `tests/` و هیچ ماژول محصولی آن را import نمی‌کند. جایگزین تزریق‌شدهٔ صریح برای `LocalPythonExecutor`. |
| `tests/test_data_science.py`, `tests/test_research_{engine,security,bridge}.py` | به‌جای تکیه بر متغیر محیطی حذف‌شده، اجراکنندهٔ تستی را **صریح تزریق** می‌کنند. |
| `tests/test_no_local_execution_fallback.py` | **جدید، ۱۹ تست** (بخش بعد). |
| `examples/research_demo.py` | سوییچ `--local-exec` حذف شد. |

### ۱۲.۲ شواهد (اجرای واقعی، بدون pytest — چون در این snapshot هیچ venv/pytest نصب نیست)

ابزار: `/home/user/p0-verification/run_new_tests_manual.py` — یک هارنس
استاندارد-کتابخانه‌ای که `monkeypatch`/`tmp_path` را شبیه‌سازی می‌کند و بدنهٔ
تست‌ها را واقعاً اجرا می‌کند (نصب هیچ بسته‌ای انجام نشد؛ طبق محدودیت شما).

```
$ python3 run_new_tests_manual.py
19 passed, 0 failed

$ python3 run_new_tests_manual.py tests.test_no_local_execution_fallback \
      tests.test_data_science tests.test_bridge_data
81 passed, 0 failed
(test_data_science: 53/53 — تست‌های pandas-gated طبق روال skip)
(research engine/security/bridge: SKIP — pandas در این محیط نیست)
```

خطوط لاگ واقعی در همین اجرا، که نشان می‌دهد مسیرها واقعاً طی شده‌اند:

```
data-science sandbox unavailable: FileNotFoundError        ← نبود باینری docker
data-science sandbox unavailable: DockerUnavailableError    ← دیمن از کار افتاد
data-science: DockerSandbox is not importable; the runtime will report
              `unavailable` and nothing will execute (no host fallback)
```

۱۹ تست جدید مستقیماً دو موردِ خواستهٔ شما را اثبات می‌کنند:

1. `DREAM_DATA_LOCAL_EXEC=1` **بی‌اثر** است و در حین بررسی هیچ فرایندی spawn
   نمی‌شود (recorder روی هر spawn استثنا می‌اندازد).
2. شکست importِ `dream.docker_sandbox` ⇒ `UnavailableCodeExecutor`، نتیجهٔ
   `available=False`/کد ۱۲۶/`docker_unavailable`، و باز هم صفر spawn.
3. `_data_call` روی همان حالت ⇒ `BridgeError(code=-32010)`، نه `INVALID_PARAMS`.
4. research پیش از نوشتن هر فایلی `ContainerUnavailableError` می‌دهد؛ دروازهٔ
   AST هم هنوز **اول** اجرا می‌شود (payload خصمانه = `ResearchSecurityError`،
   payload بی‌خطر با نبود کانتینر = `ContainerUnavailableError`).
5. `docker_available()` دیگر دروغ نمی‌گوید؛ `local-subprocess` جایی در
   `dream/research/**` نیست؛ fixture تستی از محصول import نمی‌شود.

### ۱۲.۳ آنچه در این مرحله اثبات نشد (صادقانه)

- **مسیر `FAILED` در سطح نشست** اجرا نشد: بازکردن یک نشست research به pandas
  نیاز دارد و این محیط pandas ندارد (همان دلیلی که سه فایل research در
  تست کامل هم skip می‌شوند). پوشش فعلی: (الف) اجراکننده **پیش از هر I/O** رد
  می‌کند، و (ب) یک تست ساختاری ترتیب `except ContainerUnavailableError` را
  پیش از `except Exception` قفل می‌کند.
- **کانتینر واقعی** همچنان اجرا نشد؛ همهٔ ادعاهای مربوط به کانتینر همان‌طور که
  در §۷ و §۹ گفته شد در سطح «دریم چه می‌خواهد» باقی می‌مانند.
- `pytest`/`ruff`/`npm` در این نوبت قابل اجرا نبودند (`/home/user/.venv` و
  `node_modules` در snapshot نیستند و نصب ممنوع بود). بنابراین سبزیِ کل
  مجموعه **تأییدنشده** است و باید روی ماشینی با venv اجرا شود — دستورها:
  `/home/user/.venv/bin/python -m pytest tests/test_no_local_execution_fallback.py tests/test_data_science.py tests/test_bridge_data.py -q`
  و سپس کل مجموعه با
  `/home/user/.venv/bin/python -m pytest -q -p no:cacheprovider`.
  پیش‌بینی می‌شود تست `tests/test_m16_conditional_assertions.py` سبز بماند؛
  هیچ `assert` داخل `if` در تست تازه نیست.

### ۱۲.۴ تصمیم‌های باقی‌مانده

D2 (دامنهٔ F1/F3/F5/F6)، D3 (الزام digest تصویر + مجموعهٔ تست کانتینر زنده) و
D4 (اصلاح fixture راز در `tests/test_code_execution_contract.py`) هنوز بی‌پاسخ‌اند.
