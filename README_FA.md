# 🌙 دستیار هوشمند دریم (Dream Assistant)
> **دستیار هوشمند، محلی، ایمن و مستقل با پشتیبانی کامل و درجه‌یک از زبان فارسی و تقویم جلالی**

[![CI](https://github.com/AliNaderiii/Dream/actions/workflows/ci.yml/badge.svg)](https://github.com/AliNaderiii/Dream/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 🌟 ویژگی‌های کلیدی دریم (Dream)

- 🧠 **حافظه ماندگار و هوشمند (Durable Memory):** به خاطر سپردن خودکار فکت‌ها، ترجیحات و نکات مهم کاربر در طول زمان به صورت محلی در SQLite.
- 📅 **تقویم و زمان بومی (Jalali Native):** درک کامل عبارات زمانی و تقویم هجری شمسی (جلالی)، ثبت یادآورها و محاسبات زمانی بدون خطا.
- ⚡ **رجیستری چند ارائه‌دهنده‌ای و Fallback خودکار:** اتصال مستقیم به **AvalAI**، **Anthropic Claude**، **Google Gemini**، **OpenAI**، **DeepSeek** و مدل‌های محلی **Ollama** با قابلیت جابه‌جایی خودکار در صورت قطعی یا خطا.
- 🛠️ **سیستم ماژولار ابزارها (Extensible Toolsets):** مدیریت ابزارهای محاسباتی، وب‌گردی، مدیریت فایل و یادداشت‌ها با دسته‌بندی پویا.
- 🎓 **یادگیری مهارت‌ها (Self-Learning Skills):** امکان تعریف و یادگیری مهارت‌های جدید در قالب فایل‌های متنی ساده (`SKILL.md`) توسط کاربر یا مدل.
- 🛡️ **امنیت ۵ لایه‌ای (Defense-in-Depth):** محافظت سخت‌گیرانه در برابر نشت داده، حملات تزریق پرامپت (Prompt Injection)، حملات SSRF و بلاک‌لیست قطعی دستورات خطرناک سیستم.

---

## 🚀 راهنمای نصب و راه‌اندازی سریع

### پیش‌نیازها
- پایتون نسخه **3.10** یا بالاتر
- گیت (Git)

### گام ۱: کلون کردن مخزن
```bash
git clone https://github.com/AliNaderiii/Dream.git
cd Dream
```

### گام ۲: ایجاد و فعال‌سازی محیط مجازی
**در ویندوز (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**در لینوکس / مک:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### گام ۳: نصب پکیج
```bash
pip install -e ".[dev]"
```

---

## ⚙️ پیکربندی ارائه‌دهندگان مدل (Model Providers)

شما می‌توانید کلیدهای API خود را در متغیرهای محیطی یا فایل `.env` تنظیم کنید:

### ۱. استفاده از پلتفرم ایرانی AvalAI (پیشنهادی برای ایران)
```bash
export DREAM_BACKEND="avalai"
export DREAM_AVALAI_API_KEY="your-avalai-api-key"
export DREAM_MODEL="gpt-4o-mini"
```

### ۲. استفاده از Anthropic Claude
```bash
export DREAM_BACKEND="anthropic"
export DREAM_ANTHROPIC_API_KEY="your-anthropic-api-key"
export DREAM_MODEL="claude-3-5-sonnet-20241022"
```

### ۳. استفاده از Google Gemini
```bash
export DREAM_BACKEND="gemini"
export DREAM_GEMINI_API_KEY="your-gemini-api-key"
export DREAM_MODEL="gemini-1.5-flash"
```

### ۴. استفاده از مدل‌های کاملاً محلی و آفلاین (Ollama)
```bash
export DREAM_BACKEND="ollama"
export DREAM_MODEL="llama3.1"
```

### ۵. تنظیم آبشار و جابه‌جایی خودکار (Fallback Cascade)
برای تضمین ۱۰۰٪ پایداری، می‌توانید چندین ارائه‌دهنده را با کاما جدا کنید تا در صورت اختلال یکی، دیگری بلافاصله پاسخ دهد:
```bash
export DREAM_BACKEND="avalai,anthropic,ollama"
```

---

## 💻 نحوه استفاده از خط فرمان (CLI)

### شروع گفت‌وگوی تعاملی
```bash
dream
```

### اجرای یک تسک مستقیم (تک‌دستور)
```bash
dream "یادداشتی به اسم خرید بنویس و توش شیر و نان رو ثبت کن"
```

### بررسی سلامت سیستم و ابزارها
```bash
dream /doctor
```

### مشاهده مهارت‌های نصب‌شده
```bash
dream /skills
```

### مشاهده یادآورهای فعال
```bash
dream /reminders
```

---

## 🧪 اجرای تست‌ها و بررسی کیفیت کد

پروژه دریم دارای بیش از ۳۷۰۰ تست خودکار است:

```bash
# اجرای کل تست‌های سیستم
pytest

# اجرای تست‌های واحد مربوط به Toolsets و Providers
pytest tests/test_toolsets.py tests/test_provider_registry.py tests/test_model_providers.py -v

# بررسی رعایت استانداردهای کد با Ruff
ruff check .
```

---

## 📖 مستندات بیشتر
- [سند معماری نسخه ۲.۰ دریم (Architecture Blueprint)](docs/ARCHITECTURE_V2.md)
- [راهنمای مشارکت در توسعه (CONTRIBUTING.md)](CONTRIBUTING.md)

---

## 📄 مجوز (License)
این پروژه تحت مجوز **MIT** منتشر شده است. استفاده، شخصی‌سازی و توسعه‌ی آن برای همگان آزاد و رایگان است.
