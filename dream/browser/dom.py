"""DOM cleaner, semantic markdown converter, and interactive element extractor."""

from __future__ import annotations

import re
import unicodedata

from dream.browser.types import PageElement


class DOMParser:
    """Parses raw HTML into simplified semantic markdown with labeled interactive elements."""

    def clean_html(self, html: str) -> str:
        """Strip non-content tags (scripts, styles, tracking, inline styles)."""
        pattern = r"<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>"
        cleaned = re.sub(pattern, "", html, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def extract_interactive_elements(self, html: str) -> list[PageElement]:
        """Extract interactive buttons, links, and input fields from HTML."""
        elements = []
        elem_id = 1

        # Match links
        link_pat = r'<a\s+[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>'
        for m in re.finditer(link_pat, html, re.DOTALL | re.IGNORECASE):
            href = m.group(1)
            raw_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if raw_text:
                elements.append(
                    PageElement(
                        element_id=elem_id,
                        tag_name="a",
                        text=raw_text,
                        selector=f"a[href='{href}']",
                        is_interactive=True,
                        attributes={"href": href},
                    )
                )
                elem_id += 1

        # Match buttons
        for m in re.finditer(r"<button[^>]*>(.*?)</button>", html, re.DOTALL | re.IGNORECASE):
            raw_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            text = raw_text or "Button"
            elements.append(
                PageElement(
                    element_id=elem_id,
                    tag_name="button",
                    text=text,
                    selector=f"button:has-text('{text[:20]}')",
                    is_interactive=True,
                )
            )
            elem_id += 1

        # Match input fields
        for m in re.finditer(r"<input\s+([^>]*)/?>", html, re.IGNORECASE):
            attrs = m.group(1)
            name_m = re.search(r'name=["\']([^"\']+)["\']', attrs)
            type_m = re.search(r'type=["\']([^"\']+)["\']', attrs)
            placeholder_m = re.search(r'placeholder=["\']([^"\']+)["\']', attrs)

            name = name_m.group(1) if name_m else f"input_{elem_id}"
            inp_type = type_m.group(1) if type_m else "text"
            placeholder = placeholder_m.group(1) if placeholder_m else ""

            elements.append(
                PageElement(
                    element_id=elem_id,
                    tag_name="input",
                    text=placeholder or name,
                    selector=f"input[name='{name}']",
                    is_interactive=True,
                    attributes={"type": inp_type, "name": name, "placeholder": placeholder},
                )
            )
            elem_id += 1

        return elements

    def html_to_semantic_markdown(self, html: str) -> str:
        """Convert clean HTML to readable structured Markdown."""
        text = self.clean_html(html)

        # Convert headers
        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", text, flags=re.DOTALL | re.IGNORECASE)

        # Convert paragraphs & breaks
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

        # Convert list items
        text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Normalize whitespace and unicode NFKC
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        cleaned_markdown = "\n".join(line for line in lines if line)
        norm_result = unicodedata.normalize("NFKC", cleaned_markdown)

        return norm_result
