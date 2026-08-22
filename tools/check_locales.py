#!/usr/bin/env python3
"""Fail when Dream's generated locale key trees or placeholders diverge."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALE_ROOT = REPO_ROOT / "apps" / "desktop" / "src" / "locales"
EXPECTED_LOCALES = ("en", "fa", "zh-CN", "ja", "es", "de", "fr", "ko")
PLACEHOLDER = re.compile(r"{{\s*([\w.-]+)\s*}}")


def structure(value: Any, prefix: str = "") -> dict[str, str]:
    """Return every branch/leaf path and its JSON kind."""
    if isinstance(value, dict):
        result = {prefix: "object"} if prefix else {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(structure(child, path))
        return result
    if isinstance(value, list):
        return {prefix: "array"}
    return {prefix: type(value).__name__}


def leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(leaves(child, path))
        return result
    return {prefix: value}


def fail(message: str) -> None:
    print(f"locale check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_locale(locale: str, namespaces: tuple[str, ...]) -> dict[str, Any]:
    directory = LOCALE_ROOT / locale
    files = tuple(sorted(path.stem for path in directory.glob("*.json")))
    if files != namespaces:
        fail(f"{locale} namespace files differ: expected {namespaces}, received {files}")
    return {
        namespace: json.loads((directory / f"{namespace}.json").read_text(encoding="utf-8"))
        for namespace in namespaces
    }


def main() -> None:
    locale_dirs = tuple(sorted(path.name for path in LOCALE_ROOT.iterdir() if path.is_dir()))
    if set(locale_dirs) != set(EXPECTED_LOCALES):
        fail(f"locale directories differ: expected {EXPECTED_LOCALES}, received {locale_dirs}")

    namespaces = tuple(sorted(path.stem for path in (LOCALE_ROOT / "en").glob("*.json")))
    if not namespaces:
        fail("English locale has no JSON namespaces")

    trees = {locale: load_locale(locale, namespaces) for locale in EXPECTED_LOCALES}
    english_structure = structure(trees["en"])
    english_leaves = leaves(trees["en"])

    for locale, tree in trees.items():
        candidate_structure = structure(tree)
        if candidate_structure != english_structure:
            missing = sorted(set(english_structure) - set(candidate_structure))
            extra = sorted(set(candidate_structure) - set(english_structure))
            mismatched = sorted(
                key
                for key in set(english_structure) & set(candidate_structure)
                if english_structure[key] != candidate_structure[key]
            )
            fail(
                f"{locale} key tree diverges; missing={missing[:5]}, "
                f"extra={extra[:5]}, type_mismatch={mismatched[:5]}"
            )

        candidate_leaves = leaves(tree)
        for key, english_value in english_leaves.items():
            translated_value = candidate_leaves[key]
            if isinstance(english_value, str) and isinstance(translated_value, str):
                expected = set(PLACEHOLDER.findall(english_value))
                received = set(PLACEHOLDER.findall(translated_value))
                if expected != received:
                    fail(
                        f"{locale}:{key} placeholders differ; "
                        f"expected={sorted(expected)}, received={sorted(received)}"
                    )

    print(
        "Locale integrity: PASS — "
        f"{len(EXPECTED_LOCALES)} locales × {len(namespaces)} namespaces; "
        f"{len(english_leaves)} leaves and identical key/type/placeholder trees."
    )


if __name__ == "__main__":
    main()
