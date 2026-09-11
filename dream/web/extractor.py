"""High-fidelity HTML to clean Markdown extractor with SSRF and injection protection."""

from __future__ import annotations

import html
import logging
import re
import urllib.error
import urllib.request

from dream.web.security import sanitize_extracted_web_text, validate_web_url
from dream.web.types import ExtractedWebContent

logger = logging.getLogger(__name__)

USER_AGENT = "DreamAssistant/2.0 (Web Extractor; +https://github.com/AliNaderiii/Dream)"
DEFAULT_MAX_CHARS = 8000


class WebContentExtractor:
    """Safe HTML retrieval and conversion to clean Markdown."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def extract_from_url(
        self,
        url: str,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> ExtractedWebContent:
        """Fetch URL and extract clean, sanitized Markdown."""
        # 1. SSRF Safety Verification
        try:
            safe_url = validate_web_url(url)
        except Exception as exc:
            return ExtractedWebContent(
                url=url,
                title="SSRF Error",
                markdown="",
                raw_html_bytes=0,
                cleaned_bytes=0,
                error_message=f"SSRF Refusal: {exc}",
            )

        # 2. HTTP Fetch
        try:
            req = urllib.request.Request(
                safe_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    "Accept-Language": "fa,en-US,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                raw_bytes = resp.read(2_000_000)  # Bound read to 2MB
                charset = "utf-8"
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()

                raw_html = raw_bytes.decode(charset, errors="replace")

        except Exception as exc:
            logger.error(f"Failed to fetch web content from {url}: {exc}")
            return ExtractedWebContent(
                url=url,
                title="Fetch Error",
                markdown="",
                raw_html_bytes=0,
                cleaned_bytes=0,
                error_message=str(exc),
            )

        # 3. HTML to Markdown Conversion
        return self.html_to_markdown(safe_url, raw_html, max_chars=max_chars)

    def html_to_markdown(
        self,
        url: str,
        raw_html: str,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> ExtractedWebContent:
        """Convert raw HTML string into clean Markdown text."""
        raw_len = len(raw_html.encode("utf-8"))

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        title = (
            html.unescape(title_match.group(1).strip())
            if title_match
            else "Untitled Document"
        )
        title = re.sub(r"\s+", " ", title)

        # Extract links
        links = []
        link_pat = r'<a\s+(?:[^>]*?\s+)?href=["\'](https?://[^"\']+)["\']'
        for match in re.finditer(link_pat, raw_html, re.I):
            link = match.group(1).strip()
            if link not in links and len(links) < 15:
                links.append(link)

        # Remove non-content elements
        text = raw_html
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        tag_pat = r"<(script|style|noscript|svg|canvas|form|nav|footer|header)[^>]*>.*?</\1>"
        text = re.sub(tag_pat, "", text, flags=re.DOTALL | re.I)

        # Convert headers
        for i in range(6, 0, -1):
            hashes = "#" * i
            h_pat = rf"<h{i}[^>]*>(.*?)</h{i}>"
            text = re.sub(h_pat, rf"\n\n{hashes} \1\n\n", text, flags=re.DOTALL | re.I)

        # Convert code blocks
        code_pat = r"<pre[^>]*><code[^>]*>(.*?)</code></pre>"
        text = re.sub(code_pat, r"\n\n```\n\1\n```\n\n", text, flags=re.DOTALL | re.I)
        text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.I)

        # Convert list items
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n* \1", text, flags=re.DOTALL | re.I)

        # Convert paragraphs and breaks
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\n\1\n\n", text, flags=re.DOTALL | re.I)
        text = re.sub(r"<br\s*/?>", r"\n", text, flags=re.I)
        text = re.sub(r"<hr\s*/?>", r"\n\n---\n\n", text, flags=re.I)

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)

        # Normalize whitespace and blank lines
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        cleaned_markdown = "\n".join(lines)
        cleaned_markdown = re.sub(r"\n{3,}", "\n\n", cleaned_markdown).strip()

        # 4. Truncation if exceeding budget
        is_truncated = False
        if len(cleaned_markdown) > max_chars:
            cleaned_markdown = (
                cleaned_markdown[:max_chars]
                + "\n\n... [Content Truncated / محتوا کوتاه شد]"
            )
            is_truncated = True

        # 5. Layer-5 Prompt Injection Quarantine
        sanitized_md, injection_count = sanitize_extracted_web_text(cleaned_markdown, url)

        return ExtractedWebContent(
            url=url,
            title=title,
            markdown=sanitized_md,
            raw_html_bytes=raw_len,
            cleaned_bytes=len(sanitized_md.encode("utf-8")),
            is_truncated=is_truncated,
            quarantined_injections=injection_count,
            extracted_links=links,
        )
