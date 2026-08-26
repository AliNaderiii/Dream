# تحقیق P11 — حلقهٔ زنده (نقش، پیشنویس→زمان‌بند، صداقت مسیر)

**تاریخ:** ۲۰۲۶-۰۸-۲۶  
**حکم:** الگوهای نظارت انسانی و صداقت مسیر را بگیر؛ VM ابری و لاگین به حساب واقعی را نگیر.

منابع اصلی: [Grok Bot docs](https://docs.x.ai/grok-bot/overview) · [Vellum Grok Bot](https://www.vellum.ai/blog/official-grok-bot-breakdown) · [monday agents](https://monday.com/blog/ai-agents/ai-use-cases/) · [HITL 2026](https://getclaw.sh/blog/human-in-the-loop-ai-agents-approvals-2026) · [Relay.app](https://buildrlabs.ai/tool-guide/relay-app/) · [Strands Agent SOPs](https://github.com/strands-agents/agent-sop) · [CSA Agentic Universe Apr 2026](https://labs.cloudsecurityalliance.org/agentic/agentic-universe-april-2026-v1/)

---

## ۱) بازار چه می‌گوید (اوت ۲۰۲۶)

چت تمام شد؛ محصول «همکار نام‌دار که کار را تمام می‌کند و فقط برای حکم برمی‌گردد» است.

| الگو | محصول | برای رویا |
|---|---|---|
| نقش تک‌شغله + سند دستور | Hops / Dust / Strands SOP | P10 دارد؛ P11 باید نقش را در نوبت واقعی بنشاند |
| Skill ≠ Routine | Grok Bot | «چگونه» در سند Space؛ «کی» فقط بعد از Approve به cron |
| صف پیشنویس، بعد تأیید | monday · Relay · OpenAI Agents SDK | P10 پیشنویس دارد؛ P11 به `create_schedule` وصل می‌کند |
| تأیید هر اجرا، حتی بعد از Approve قاعده | Grok Allow once / monday HITL | `require_approval=True` روی زمان‌بند زنده |
| صداقت مسیر مدل | Bifrost `extra_fields.provider` · LLM Status | نوار وضعیت نباید Echo بگوید وقتی پنل Earth Runtime است |
| VM ابری + لاگین واقعی | Grok Bot (یک VM برای همهٔ Botها) | **نه** — docs خودشان می‌گویند Bot مرز امنیتی نیست |

Relay.app جولای ۲۰۲۶ تعطیل شد؛ ایدهٔ «pause برای انسان وسط اجرا» زنده ماند و monday همان را در آگوست ۲۰۲۶ به AI Workflows آورد.

CSA: ریسک HITL = خستگی تأیید + دور زدن تأیید. کنترل: متن کامل اقدام، نه خلاصه؛ timeout؛ ممیزی approve→action.

چهار سطح تأیید (Claw / StackAI):

0. Autopilot — خواندن/خلاصه  
1. Batch — پیشنویس‌های برگشت‌پذیر  
2. یکی‌یکی — پول، ارسال، production  
3. فقط انسان — حقوقی / بانکی  

P11 رویا: سطح ۲ برای مسلح‌کردن قاعده؛ سطح ۲ دوباره برای هر شلیک cron.

---

## ۲) شکاف رویا بعد از P9/P10

- پیشنویس تأییدشده **شلیک نمی‌شود** (`run_draft` صریح می‌گوید residual).
- `space.ask` briefing محلی است؛ Earth Runtime در پنل چت جداست.
- نوار وضعیت `activeProviderId` فروشگاه Settings است (پیش‌فرض `Echo (offline)`). پنل چت مدل خودش را دارد. این دروغ محصول است، نه قطع موتور.
- نصب ۰.۴.۲ این کد را ندارد.

---

## ۳) برش P11 (یک PR)

1. **Arm.** پیشنویس `APPROVED` + cron معتبر + غیرخطرناک → `dream.scheduler.create_schedule(..., require_approval=True)`. خطرناک هرگز زمان‌بندی نمی‌شود.
2. **Role turn.** نوبت نقش با سقف ریسک و سند دستور. `live=false` پیش‌فرض (قابل‌آزمون). `live=true` بدون کلید/شبکه fail-closed.
3. **Honesty.** `liveloop.route_snapshot` + نشان نوار: «این Settings است، نه پنل چت».

خارج از محدوده: computer-use، VM ابری، teach-by-demo مرورگر، سیم‌کشی P5 parser / P6 L9 / P7 به agent.py.

---

## ۴) آنچه هرگز کپی نمی‌شود

- لاگین ابری به Gmail/CRM
- چند نقش روی یک نشست مشترک به‌عنوان مرز امنیتی
- Always Allow پهن («همهٔ ابزار آزاد»)
- پنهان‌کردن fallback به echo
