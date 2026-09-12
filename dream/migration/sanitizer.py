"""Data sanitization, Persian text normalization, and path security for migration."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from dream.security.pathsafety import is_sensitive_path


class MigrationSanitizer:
    """Guards against malicious payloads, path traversals, and corrupted encodings."""

    @staticmethod
    def is_safe_source_path(path_str: str) -> bool:
        """Verify the path is not a forbidden OS system directory."""
        if not path_str or not path_str.strip():
            return False
        clean = path_str.strip()
        if ".." in clean:
            return False
        return not is_sensitive_path(clean)

    @staticmethod
    def normalize_persian_text(text: str) -> tuple[str, int]:
        """Normalize Persian typography, replace Arabic chars (ي, ك), and balance ZWNJ.

        Returns:
            Tuple of (normalized_text, number_of_characters_modified)
        """
        if not text:
            return "", 0

        # Step 1: NFKC unicode normalization
        nfkc_text = unicodedata.normalize("NFKC", text)

        # Step 2: Arabic character folding to standard Persian
        replacements = {
            "ي": "ی",
            "ى": "ی",
            "ك": "ک",
            "ئ": "ی",
            "۰": "0",
            "۱": "1",
            "۲": "2",
            "۳": "3",
            "۴": "4",
            "۵": "5",
            "۶": "6",
            "۷": "7",
            "۸": "8",
            "۹": "9",
            "–": "-",
            "—": "-",
            "…": "...",
        }

        changes_count = 0
        buf: list[str] = []
        for ch in nfkc_text:
            if ch in replacements:
                buf.append(replacements[ch])
                changes_count += 1
            else:
                buf.append(ch)

        res = "".join(buf)

        # Step 3: Standardize common Persian verb half-spaces
        zwnj_pat = re.compile(r"\b(می|نمی)\s+([^\s]+)")
        if zwnj_pat.search(res):
            res, count = zwnj_pat.subn(r"\1‌\2", res)
            changes_count += count

        return res, changes_count

    @staticmethod
    def sanitize_file_name(filename: str) -> str:
        """Produce a safe filesystem name by removing path separators and shell characters."""
        clean = Path(filename).name
        clean = re.sub(r'[\\/*?:"<>|]', "_", clean)
        return clean.strip() or "migrated_item.md"
