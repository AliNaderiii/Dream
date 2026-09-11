"""Slash command handler for web searching and browsing."""

from __future__ import annotations

from collections.abc import Callable

from dream.web.tools import get_web_manager


def handle_search_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/search <query>` slash command."""
    query = args.strip()
    if not query:
        output("راهنمای دستور جستجو / Search Help:\n  /search <کلمه کلیدی>")
        return True

    mgr = get_web_manager()
    output(f"🔍 در حال جستجوی `{query}` در وب...\n")
    res = mgr.search(query, max_results=5)

    if not res.is_success or not res.results:
        output(f"نتیجه‌ای یافت نشد یا خطایی رخ داد: {res.error_message or 'No results'}")
        return True

    output(f"🌐 **یافته‌های وب ({res.backend.value}) — {len(res.results)} نتیجه:**\n")
    for i, item in enumerate(res.results, 1):
        output(f"{i}. **[{item.title}]({item.url})**\n   {item.snippet}\n")
    return True


def handle_browse_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/browse <url>` slash command."""
    url = args.strip()
    if not url:
        output("راهنمای مرور وب / Browse Help:\n  /browse <https://example.com>")
        return True

    mgr = get_web_manager()
    output(f"🌐 در حال دریافت و استخراج محتوای `{url}`...\n")
    content = mgr.extract_url(url)

    if content.error_message:
        output(f"❌ خطا در دریافت صفحه: {content.error_message}")
        return True

    output(f"📄 **{content.title}**\n\n{content.markdown}\n")
    if content.quarantined_injections > 0:
        output(f"⚠️ {content.quarantined_injections} الگوی تزریق پرامپت مشکوک خنثی شد.")
    return True
