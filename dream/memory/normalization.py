"""Persian and Arabic text normalization, tokenization, stemming and synonym index."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence

DEFAULT_CONTRADICTION_THRESHOLD = 0.80
_MIN_CONTRADICTION_PREFIX_TOKENS = 2
DEFAULT_DUPLICATE_THRESHOLD = 0.80

_DIGIT_MAP = {
    **{0x06F0 + i: ord("0") + i for i in range(10)},
    **{0x0660 + i: ord("0") + i for i in range(10)},
}

_CHAR_MAP = {
    0x064A: 0x06CC,  # ARABIC YEH        -> FARSI YEH
    0x0649: 0x06CC,  # ALEF MAKSURA      -> FARSI YEH
    0x0643: 0x06A9,  # ARABIC KAF        -> KEHEH
    0x0629: 0x0647,  # TEH MARBUTA       -> HEH
    0x0623: 0x0627,  # ALEF WITH HAMZA ABOVE -> ALEF
    0x0625: 0x0627,  # ALEF WITH HAMZA BELOW -> ALEF
    0x0622: 0x0627,  # ALEF WITH MADDA ABOVE -> ALEF
    0x0624: 0x0648,  # WAW WITH HAMZA    -> WAW
    0x0626: 0x06CC,  # YEH WITH HAMZA    -> FARSI YEH
}

_DIACRITICS = {cp: None for cp in range(0x064B, 0x0653)}
_DIACRITICS[0x0670] = None
_DIACRITICS[0x0640] = None

_ZWNJ = "\u200c"
_WS_RE = re.compile(r"\s+")


def normalize_fa(text: str) -> str:
    """Normalise Persian/Arabic text to one canonical spelling."""
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = out.translate(_DIGIT_MAP)
    out = out.translate(_CHAR_MAP)
    out = out.translate(_DIACRITICS)
    out = out.replace(_ZWNJ, " ")
    return _WS_RE.sub(" ", out).strip()


def _resolve_contradiction_threshold(raw: str | None) -> float:
    if not raw:
        return DEFAULT_CONTRADICTION_THRESHOLD
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_CONTRADICTION_THRESHOLD
    if not 0.0 <= value <= 1.0:
        return DEFAULT_CONTRADICTION_THRESHOLD
    return value


def _resolve_duplicate_threshold(raw: str | None) -> float:
    if not raw:
        return DEFAULT_DUPLICATE_THRESHOLD
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_DUPLICATE_THRESHOLD
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        return DEFAULT_DUPLICATE_THRESHOLD
    return value


_SUFFIXES: tuple[str, ...] = (
    "هایمان",
    "هایتان",
    "هایشان",
    "هایی",
    "هایم",
    "هایت",
    "هایش",
    "مان",
    "تان",
    "شان",
    "های",
    "ها",
    "ترین",
    "تر",
    "ام",
    "ات",
    "اش",
    "ی",
    "م",
    "ت",
    "ش",
)


def _stem_fa(token: str) -> str:
    """Strip one Persian suffix when a meaningful stem remains."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix):
            stem = token[: -len(suffix)]
            if len(stem) > 2:
                return stem
    return token


_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_fa(text))


def _stemmed_tokens(text: str) -> list[str]:
    return [_stem_fa(token) for token in _tokenize(text)]


def _is_contradiction(old: str, new: str, threshold: float) -> bool:
    old_tokens = _stemmed_tokens(old)
    new_tokens = _stemmed_tokens(new)
    common_prefix = 0
    for old_token, new_token in zip(old_tokens, new_tokens, strict=False):
        if old_token != new_token:
            break
        common_prefix += 1

    if common_prefix < _MIN_CONTRADICTION_PREFIX_TOKENS:
        return False
    if common_prefix == min(len(old_tokens), len(new_tokens)):
        return False
    return common_prefix / max(len(old_tokens), len(new_tokens)) >= threshold


def _fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("\u0646\u0627\u0645", "\u0627\u0633\u0645"),
    ("\u0634\u063a\u0644", "\u06a9\u0627\u0631", "\u062d\u0631\u0641\u0647"),
    ("\u062e\u0627\u0646\u0647", "\u0645\u0646\u0632\u0644"),
    ("\u0647\u0645\u0633\u0631", "\u0632\u0646", "\u0634\u0648\u0647\u0631"),
    (
        "\u062e\u0648\u062f\u0631\u0648",
        "\u0645\u0627\u0634\u06cc\u0646",
        "\u0627\u062a\u0648\u0645\u0628\u06cc\u0644",
    ),
    (
        "\u062a\u0644\u0641\u0646",
        "\u06af\u0648\u0634\u06cc",
        "\u0645\u0648\u0628\u0627\u06cc\u0644",
    ),
    ("\u0634\u0647\u0631", "\u0634\u0647\u0631\u0633\u062a\u0627\u0646"),
    ("\u0633\u0646", "\u0639\u0645\u0631"),
    ("\u062f\u0648\u0633\u062a", "\u0631\u0641\u06cc\u0642"),
    ("\u067e\u0648\u0644", "\u0648\u062c\u0647"),
    ("\u062f\u0631\u0622\u0645\u062f", "\u062d\u0642\u0648\u0642"),
    ("\u0622\u062f\u0631\u0633", "\u0646\u0634\u0627\u0646\u06cc"),
    ("\u062a\u0648\u0644\u062f", "\u0632\u0627\u062f\u0631\u0648\u0632"),
    ("\u062e\u0627\u0646\u0648\u0627\u062f\u0647", "\u0641\u0627\u0645\u06cc\u0644"),
    ("\u0628\u0686\u0647", "\u0641\u0631\u0632\u0646\u062f"),
    ("\u062f\u0641\u062a\u0631", "\u0627\u062f\u0627\u0631\u0647"),
    ("\u06a9\u06cc", "\u06a9\u0627\u0631\u0628\u0631"),
)


def _load_extra_synonym_groups() -> tuple[tuple[str, ...], ...]:
    path = os.environ.get("DREAM_SYNONYMS", "")
    if not path:
        return ()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ()
    if not isinstance(data, list):
        return ()
    for group in data:
        if not isinstance(group, list) or not all(isinstance(w, str) for w in group):
            return ()
    return tuple(tuple(group) for group in data)


def _build_synonym_index(
    groups: Iterable[Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    index: dict[str, tuple[str, ...]] = {}
    for group in groups:
        members: list[str] = []
        for word in group:
            for token in _tokenize(word):
                stem = _stem_fa(token)
                if stem not in members:
                    members.append(stem)
        member_tuple = tuple(members)
        for word in group:
            for token in _tokenize(word):
                index[_stem_fa(token)] = member_tuple
    return index


_SYNONYM_INDEX: dict[str, tuple[str, ...]] = _build_synonym_index(
    (*_SYNONYM_GROUPS, *_load_extra_synonym_groups())
)

_EXCLUDED_FROM_DUPLICATE_CANONICALISATION: frozenset[str] = frozenset(
    ["\u0647\u0645\u0633\u0631", "\u0632\u0646", "\u0634\u0648\u0647\u0631"]
)


def _build_canonical_map(
    groups: Iterable[Sequence[str]],
    excluded: frozenset[str],
) -> dict[str, str]:
    canonical: dict[str, str] = {}
    for group in groups:
        if any(word in excluded for word in group):
            continue
        members: list[str] = []
        for word in group:
            for token in _tokenize(word):
                stem = _stem_fa(token)
                if stem not in members:
                    members.append(stem)
        if not members:
            continue
        representative = min(members)
        for stem in members:
            canonical[stem] = representative
    return canonical


def _canonicalise_stems(stems: list[str], canonical_map: dict[str, str]) -> list[str]:
    return [canonical_map.get(stem, stem) for stem in stems]


def _longest_common_subsequence(x: Sequence[str], y: Sequence[str]) -> int:
    if not x or not y:
        return 0
    if len(x) < len(y):
        x, y = y, x
    n = len(y)
    prev_row = [0] * (n + 1)
    curr_row = [0] * (n + 1)
    for item_x in x:
        for j, item_y in enumerate(y):
            if item_x == item_y:
                curr_row[j + 1] = prev_row[j] + 1
            else:
                curr_row[j + 1] = max(prev_row[j + 1], curr_row[j])
        prev_row, curr_row = curr_row, prev_row
    return prev_row[n]


def _is_duplicate(
    old: str | Sequence[str],
    new: str | Sequence[str],
    threshold: float,
    canonical_map: dict[str, str],
) -> bool:
    old_stems = (
        _canonicalise_stems(_stemmed_tokens(old), canonical_map)
        if isinstance(old, str)
        else old
    )
    new_stems = (
        _canonicalise_stems(_stemmed_tokens(new), canonical_map)
        if isinstance(new, str)
        else new
    )
    old_set = set(old_stems)
    new_set = set(new_stems)
    if not old_set or not new_set:
        return False
    intersection = len(old_set & new_set)
    union = len(old_set | new_set)
    if intersection / union < threshold:
        return False

    old_counts = Counter(old_stems)
    new_counts = Counter(new_stems)
    multiset_intersection = sum((old_counts & new_counts).values())
    return _longest_common_subsequence(old_stems, new_stems) == multiset_intersection


_CANONICAL_MAP: dict[str, str] = _build_canonical_map(
    (*_SYNONYM_GROUPS, *_load_extra_synonym_groups()),
    _EXCLUDED_FROM_DUPLICATE_CANONICALISATION,
)


def build_match_query(query: str) -> str:
    import dream.memory as memory_mod

    synonym_index = getattr(memory_mod, "_SYNONYM_INDEX", _SYNONYM_INDEX)
    clauses: list[str] = []
    seen: set[str] = set()
    for token in _tokenize(query):
        stem = _stem_fa(token)
        expanded = [_fts_escape(token), _fts_escape(stem) + "*"]
        for synonym in synonym_index.get(stem, ()):
            expanded.append(_fts_escape(synonym))
            expanded.append(_fts_escape(synonym) + "*")
        for clause in expanded:
            if clause not in seen:
                seen.add(clause)
                clauses.append(clause)
    return " OR ".join(clauses)
