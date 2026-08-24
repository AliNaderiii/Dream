"""Hardline blocklist — the non-overridable security floor (layer L3).

This module is the floor of Dream's defense-in-depth model: it is evaluated
BEFORE any approval logic and cannot be overridden by ``off`` mode, cron
approve-modes, ``--yolo``/always-allow flags, or a human approver saying
yes. A matched command is refused with a bilingual message naming the
matched class; the refusal is logged through the approval history.

Design rules:

* Data-driven: each rule is a :class:`BlockRule` entry binding a class name
  (English + Persian) to a detector over a normalized view of the command.
* Over-blocking is acceptable at the floor; under-blocking is not. Dream has
  no legitimate business wiping filesystem roots, formatting disks, writing
  raw block devices, forkbombing, piping remote pages into shells, or
  deleting registry hives. An owner who truly needs such a command runs it
  in their own terminal, not through Dream.
* Obfuscation is expected: the scanner folds zero-width/bidi controls,
  full-width and Cyrillic lookalikes, Arabic/Persian letter and digit
  variants (via the shared Persian normalizer), shell quoting and
  backslash escapes, ``~``/``$HOME``/``%USERPROFILE%``-style expansion,
  separator differences and ``..`` path normalization.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass

from dream.memory import normalize_fa

__all__ = [
    "BlockMatch",
    "BlockRule",
    "RULES",
    "ScanText",
    "floor_refusal",
    "scan",
]

# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #

#: Zero-width, directional, and invisible formatting characters. They carry
#: no command meaning but can hide a payload from a human reviewer, so they
#: are stripped before any matching happens.
_INVISIBLE_CODEPOINTS = (
    "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff"
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u00ad"
)
_INVISIBLE_TABLE = str.maketrans({char: "" for char in _INVISIBLE_CODEPOINTS})

#: Cyrillic letters that impersonate ASCII ones in command verbs and paths.
#: NFKC does not fold these, so the floor maps them explicitly.
_CYRILLIC_LOOKALIKES = str.maketrans(
    {
        "\u0430": "a",
        "\u0432": "b",
        "\u0435": "e",
        "\u043a": "k",
        "\u043c": "m",
        "\u043e": "o",
        "\u0440": "p",
        "\u0441": "c",
        "\u0442": "t",
        "\u0445": "x",
        "\u0443": "y",
        "\u0456": "i",
        "\u0458": "j",
        "\u04bb": "h",
        "\u0501": "d",
        "\u051b": "q",
        "\u051d": "w",
    }
)

#: Canonical stand-ins used when expanding home/root variables. They are
#: never executed; they exist so path matchers have a stable spelling.
_HOME_POSIX = "/home/dream"
_HOME_WINDOWS = "c:/users/dream"

_BLOCK_DEVICE_RE = re.compile(
    r"/dev/(?:sd[a-z]+\d*|hd[a-z]+\d*|nvme\d+n\d+(?:p\d+)?|vd[a-z]+\d*|xvd[a-z]+\d*"
    r"|mmcblk\d+(?:p\d+)?|disk\d+(?:s\d+)?|mapper/[a-z0-9_.-]+|dm-\d+|md\d+(?:p\d+)?)"
    r"(?![a-z0-9])"
)


def _strip_quotes(text: str) -> str:
    """Drop quote characters only, keeping backslashes (Windows separators)."""
    return text.replace('"', "").replace("'", "")


def _dequote(text: str) -> str:
    """Strip shell quoting and backslash escapes from a folded command.

    ``r''m -rf /`` and ``r\\m -rf /`` are the same verb to the shell as
    ``rm -rf /``. Dropping quotes also exposes payloads hidden inside quoted
    arguments, which is exactly what the floor wants: over-blocking a quoted
    mention is acceptable, missing a quoted payload is not. This POSIX view
    is paired with a backslash-preserving view for Windows paths.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index += 1
            continue
        if char == "\\" and index + 1 < len(text) and text[index + 1] != "\n":
            out.append(text[index + 1])
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _expand_variables(text: str) -> str:
    """Fold home/system variables to canonical paths before path matching."""
    text = re.sub(r"%HOMEDRIVE%%HOMEPATH%", _HOME_WINDOWS, text, flags=re.IGNORECASE)
    text = re.sub(r"%(?:USERPROFILE|HOMEPATH|HOMEDRIVE)%", _HOME_WINDOWS, text, flags=re.IGNORECASE)
    text = re.sub(r"%(?:SystemRoot|WINDIR|windir)%", "c:/windows", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\$env:(?:SystemRoot|windir)\b", "c:/windows", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\$env:USERPROFILE\b", _HOME_WINDOWS, text, flags=re.IGNORECASE)
    text = re.sub(r"\$\{?HOME\}?", _HOME_POSIX, text)
    text = text.replace("~", _HOME_POSIX)
    return text


#: Shell control operators become standalone tokens so ``echo x; rm -rf /``
#: splits into two simple commands even when no space surrounds the ``;``.
_OPERATOR_SPLIT_RE = re.compile(r"(\|\||&&|[;|&])")


def _split_operators(text: str) -> list[str]:
    return _OPERATOR_SPLIT_RE.sub(r" \1 ", text).split()


def _build_scan_text(command: str) -> ScanText:
    folded = str(command).translate(_INVISIBLE_TABLE)
    folded = normalize_fa(folded)
    folded = folded.translate(_CYRILLIC_LOOKALIKES)
    dequoted = _dequote(folded)
    quoted_only = _strip_quotes(folded)
    expanded = _expand_variables(dequoted)
    expanded_win = _expand_variables(quoted_only)
    flat = expanded.replace("\\", "/")
    flat_win = expanded_win.replace("\\", "/")
    tokens = _split_operators(dequoted)
    win_tokens = [token.lower() for token in _split_operators(expanded_win)]
    return ScanText(
        raw=str(command),
        folded=folded,
        dequoted=dequoted,
        expanded=expanded,
        flat=flat,
        flat_win=flat_win,
        win_tokens=win_tokens,
        tokens=tokens,
        lower_tokens=[token.lower() for token in tokens],
    )


@dataclass(frozen=True)
class ScanText:
    """One normalized view of a candidate command for the floor detectors."""

    raw: str
    folded: str
    dequoted: str
    expanded: str
    flat: str
    #: Backslash-preserving expansion, lower-cased and split: Windows paths
    #: keep their separators here (the POSIX dequote view eats them).
    flat_win: str
    win_tokens: list[str]
    tokens: list[str]
    lower_tokens: list[str]


# --------------------------------------------------------------------------- #
# Protected targets
# --------------------------------------------------------------------------- #

#: POSIX paths whose recursive deletion destroys the system or every user.
POSIX_ROOT_TARGETS = frozenset(
    {
        "/",
        "/home",
        "/usr",
        "/bin",
        "/sbin",
        "/etc",
        "/boot",
        "/lib",
        "/lib64",
        "/var",
        "/opt",
        "/system",
        "/library",
    }
)

#: Windows directories that qualify a recursive delete as a floor event.
WINDOWS_SYSTEM_DIRS = frozenset(
    {
        "c:/windows",
        "c:/program files",
        "c:/program files (x86)",
        "c:/users",
        "c:/boot",
        "c:/perflogs",
    }
)

_REGISTRY_HIVES = frozenset(
    {
        "hklm",
        "hkey_local_machine",
        "hkcr",
        "hkey_classes_root",
        "hku",
        "hkey_users",
        "hkcc",
        "hkey_current_config",
        "hkcu",
        "hkey_current_user",
    }
)

_SHELL_INTERPRETERS = frozenset(
    {"sh", "bash", "zsh", "dash", "ksh", "fish", "python", "python3", "perl", "node", "pwsh"}
)

_DRIVE_ROOT_RE = re.compile(r"^[a-z]:/?$")
_DRIVE_ANY_RE = re.compile(r"^[a-z]:")


def _canonical_target(token: str) -> str:
    """Fold one path token to a stable lower-cased spelling for matching.

    Trailing wildcards and separators are dropped, then ``..`` segments are
    normalized so ``/etc/../`` and ``/tmp/..`` both resolve to their true
    location before the target sets are consulted.
    """
    target = token.strip("\"'").lower().replace("\\", "/")
    target = target.rstrip("/*") or "/"
    if "/" in target:
        target = posixpath.normpath(target)
    return target


def _is_posix_root_target(target: str) -> bool:
    expanded = _expand_variables(target).replace("\\", "/")
    canonical = _canonical_target(expanded)
    # The Windows home counts as a home everywhere: a POSIX shell given
    # %USERPROFILE% should not slip past the floor on spelling alone.
    return (
        canonical in POSIX_ROOT_TARGETS
        or canonical == _HOME_POSIX
        or canonical == _HOME_WINDOWS
    )


def _is_windows_root_target(target: str) -> bool:
    expanded = _expand_variables(target).replace("\\", "/")
    canonical = _canonical_target(expanded)
    return (
        bool(_DRIVE_ROOT_RE.match(canonical))
        or canonical in WINDOWS_SYSTEM_DIRS
        or canonical == _HOME_WINDOWS
    )


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #


def _rm_style_flags(tokens: list[str]) -> tuple[bool, bool]:
    """Parse recursive/force flags from combined and separated rm-style forms."""
    recursive = force = False
    for token in tokens:
        if token in ("--recursive", "-recursive"):
            recursive = True
        elif token in ("--force", "-force"):
            force = True
        elif token.startswith("-") and not token.startswith("--") and len(token) > 1:
            if "r" in token or "R" in token:
                recursive = True
            if "f" in token:
                force = True
    return recursive, force


def _command_segments(tokens: list[str]) -> list[list[str]]:
    """Split a token stream into simple-command segments at && || ; newlines."""
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in ("&&", "||", ";", "&", "|"):
            segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _detect_posix_root_wipe(text: ScanText) -> str | None:
    if "--no-preserve-root" in text.lower_tokens:
        return "--no-preserve-root"
    for segment in _command_segments(text.tokens):
        verb = segment[0].rsplit("/", 1)[-1].lower()
        if verb == "rm":
            recursive, _force = _rm_style_flags(segment[1:])
            if not recursive:
                continue
            for target in segment[1:]:
                if target.startswith("-"):
                    continue
                if _is_posix_root_target(target):
                    return f"rm -r {target}"
        elif verb == "rmdir":
            for target in segment[1:]:
                if target.startswith("-"):
                    continue
                if _is_posix_root_target(target):
                    return f"rmdir {target}"
        elif verb == "find":
            has_delete = "-delete" in segment or ("-exec" in segment and "rm" in segment)
            if has_delete:
                for target in segment[1:]:
                    if target.startswith("-"):
                        break
                    if _is_posix_root_target(target):
                        return f"find {target} -delete"
    return None


def _windows_target_runs(segment: list[str]) -> list[list[str]]:
    """Group consecutive non-flag tokens: an unquoted path with spaces."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in segment[1:]:
        if token.startswith("/"):
            if current:
                runs.append(current)
                current = []
            continue
        current.append(token)
    if current:
        runs.append(current)
    return runs


def _windows_run_matches(runs: list[list[str]]) -> str | None:
    for run in runs:
        candidates = list(run) + [" ".join(run)] if len(run) > 1 else list(run)
        for target in candidates:
            if _is_windows_root_target(target):
                return target
    return None


def _detect_windows_root_wipe(text: ScanText) -> str | None:
    for segment in _command_segments(text.win_tokens):
        verb = segment[0]
        if verb in ("rd", "rmdir", "del", "erase"):
            recursive = any(
                token.startswith("/") and "s" in token for token in segment[1:]
            )
            if not recursive:
                continue
            target = _windows_run_matches(_windows_target_runs(segment))
            if target is not None:
                return f"{verb} {target}"
    return None


_PS_RECURSIVE_SHORT = re.compile(r"^-(?:r|fr|rf)$")


def _detect_powershell_root_wipe(text: ScanText) -> str | None:
    for segment in _command_segments(text.win_tokens):
        verb = segment[0]
        if verb not in ("remove-item", "rm", "ri", "rmdir", "rd"):
            continue
        recursive = any(
            token == "-r"
            or token.startswith("-recurse")
            or bool(_PS_RECURSIVE_SHORT.match(token))
            or (token.startswith("/") and "s" in token[1:])
            for token in segment[1:]
        )
        if not recursive:
            continue
        targets: list[list[str]] = []
        current: list[str] = []
        skip_next = False
        for token in segment[1:]:
            if skip_next:
                current.append(token)
                skip_next = False
                continue
            if token in ("-path", "-literalpath"):
                skip_next = True
                continue
            if token.startswith("-"):
                if current:
                    targets.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            targets.append(current)
        for run in targets:
            # Test each token alone and the whole run joined: an unquoted
            # "C:\Program Files" arrives as two tokens but names one path.
            candidates = list(run) + [" ".join(run)] if len(run) > 1 else list(run)
            for target in candidates:
                if _is_windows_root_target(target):
                    return f"{verb} {target}"
    return None


def _detect_disk_format(text: ScanText) -> str | None:
    for segment in _command_segments(text.lower_tokens):
        verb = segment[0]
        if verb == "format":
            for target in segment[1:]:
                if target in ("/?", "-?"):
                    continue
                if _DRIVE_ANY_RE.match(target.rstrip("/")):
                    return f"format {target}"
        elif verb.startswith("mkfs"):
            for target in segment[1:]:
                if target.startswith("-"):
                    continue
                if target == "/" or _BLOCK_DEVICE_RE.search(_canonical_target(target)):
                    return f"{verb} {target}"
    return None


def _detect_raw_block_write(text: ScanText) -> str | None:
    for segment in _command_segments(text.lower_tokens):
        if segment[0] == "dd":
            for token in segment[1:]:
                if token.startswith("of=") and _BLOCK_DEVICE_RE.search(token[3:]):
                    return f"dd {token}"
    redirect = re.search(r">\s*(" + _BLOCK_DEVICE_RE.pattern + r")", text.flat_win.lower())
    if redirect:
        return f"> {redirect.group(1)}"
    return None


_FORK_BOMB_RE = re.compile(r":\s*\(\s*\)\s*\{[^}]*\|[^}]*&[^}]*\}\s*;?\s*:")


def _detect_fork_bomb(text: ScanText) -> str | None:
    if _FORK_BOMB_RE.search(text.dequoted):
        return ":(){:|:&};:"
    if re.search(r"%0\s*\|\s*%0", text.dequoted, flags=re.IGNORECASE):
        return "%0|%0"
    return None


_WGET_STDOUT_RE = re.compile(r"-[a-z]*o-")


def _detect_remote_pipe_to_shell(text: ScanText) -> str | None:
    lowered = text.flat.lower()
    if re.search(r"\binvoke-expression\b|\biex\b", lowered) and re.search(
        r"downloadstring|invoke-webrequest|\biwr\b|invoke-restmethod|\birm\b|net\.webclient",
        lowered,
    ):
        return "Invoke-Expression of a remote payload"
    for left, right in zip(lowered.split("|"), lowered.split("|")[1:], strict=False):
        fetch = re.search(r"\b(curl|wget|fetch)\b", left)
        if fetch is None:
            continue
        if fetch.group(1) == "wget" and not _WGET_STDOUT_RE.search(left.replace(" ", "")):
            continue
        right_tokens = [token for token in right.split() if token]
        index = 0
        while index < len(right_tokens) and right_tokens[index] in ("sudo", "doas"):
            index += 1
        while index < len(right_tokens) and "=" in right_tokens[index]:
            index += 1
        if index < len(right_tokens):
            interpreter = right_tokens[index].rsplit("/", 1)[-1]
            if interpreter in _SHELL_INTERPRETERS:
                return f"{fetch.group(1)} … | {interpreter}"
    return None


def _detect_registry_hive_delete(text: ScanText) -> str | None:
    for segment in _command_segments(text.lower_tokens):
        if len(segment) >= 3 and segment[0] == "reg" and segment[1] == "delete":
            for target in segment[2:]:
                if target.startswith("/"):
                    continue
                if target.rstrip("\\") in _REGISTRY_HIVES:
                    return f"reg delete {target}"
    return None


# --------------------------------------------------------------------------- #
# Rules (data-driven floor)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BlockRule:
    """One floor rule: a bilingual class name bound to a detector."""

    rule_id: str
    rule_class: str
    name_en: str
    name_fa: str
    detect: Callable[[ScanText], str | None]


RULES: tuple[BlockRule, ...] = (
    BlockRule(
        rule_id="L3-01",
        rule_class="filesystem_root_wipe",
        name_en="filesystem root wipe",
        name_fa=(
            "\u062d\u0630\u0641 \u0645\u062d\u062a\u0648\u06cc\u0627\u062a "
            "\u0631\u06cc\u0634\u0647\u200c\u06cc \u0633\u06cc\u0633\u062a\u0645"
        ),
        detect=_detect_posix_root_wipe,
    ),
    BlockRule(
        rule_id="L3-02",
        rule_class="filesystem_root_wipe",
        name_en="filesystem root wipe",
        name_fa=(
            "\u062d\u0630\u0641 \u0645\u062d\u062a\u0648\u06cc\u0627\u062a "
            "\u0631\u06cc\u0634\u0647\u200c\u06cc \u0633\u06cc\u0633\u062a\u0645"
        ),
        detect=_detect_windows_root_wipe,
    ),
    BlockRule(
        rule_id="L3-03",
        rule_class="filesystem_root_wipe",
        name_en="filesystem root wipe",
        name_fa=(
            "\u062d\u0630\u0641 \u0645\u062d\u062a\u0648\u06cc\u0627\u062a "
            "\u0631\u06cc\u0634\u0647\u200c\u06cc \u0633\u06cc\u0633\u062a\u0645"
        ),
        detect=_detect_powershell_root_wipe,
    ),
    BlockRule(
        rule_id="L3-04",
        rule_class="disk_format",
        name_en="disk format",
        name_fa=(
            "\u0641\u0631\u0645\u062a \u06a9\u0631\u062f\u0646 "
            "\u062f\u06cc\u0633\u06a9"
        ),
        detect=_detect_disk_format,
    ),
    BlockRule(
        rule_id="L3-05",
        rule_class="raw_block_write",
        name_en="raw block-device write",
        name_fa=(
            "\u0646\u0648\u0634\u062a\u0646 \u0645\u0633\u062a\u0642\u06cc\u0645 "
            "\u0631\u0648\u06cc \u062f\u06cc\u0633\u06a9"
        ),
        detect=_detect_raw_block_write,
    ),
    BlockRule(
        rule_id="L3-06",
        rule_class="fork_bomb",
        name_en="fork bomb",
        name_fa=(
            "\u0628\u0645\u0628 "
            "\u0641\u0631\u0622\u06cc\u0646\u062f\u06cc"
        ),
        detect=_detect_fork_bomb,
    ),
    BlockRule(
        rule_id="L3-07",
        rule_class="remote_pipe_to_shell",
        name_en="remote code piped into a shell",
        name_fa=(
            "\u0627\u062c\u0631\u0627\u06cc \u06a9\u062f \u062f\u0648\u0631\u0627\u0647 "
            "\u062f\u0631 \u067e\u0648\u0633\u062a\u0647"
        ),
        detect=_detect_remote_pipe_to_shell,
    ),
    BlockRule(
        rule_id="L3-08",
        rule_class="registry_hive_delete",
        name_en="registry hive deletion",
        name_fa=(
            "\u062d\u0630\u0641 \u06a9\u0646\u062f\u0648\u06cc "
            "\u0631\u062c\u06cc\u0633\u062a\u0631\u06cc"
        ),
        detect=_detect_registry_hive_delete,
    ),
)


@dataclass(frozen=True)
class BlockMatch:
    """The floor's verdict on one command: which rule fired and why."""

    rule: BlockRule
    evidence: str

    @property
    def message_en(self) -> str:
        return (
            f"blocked by the security floor: {self.rule.name_en} "
            f"[{self.rule.rule_id}]. This class of command can never be approved."
        )

    @property
    def message_fa(self) -> str:
        return (
            "\u0645\u0633\u062f\u0648\u062f \u0628\u0647\u200c\u062f\u0644\u06cc\u0644 "
            "\u0645\u062d\u062f\u0648\u062f\u06cc\u062a \u0627\u0645\u0646\u06cc: "
            f"{self.rule.name_fa} [{self.rule.rule_id}]. "
            "\u0627\u06cc\u0646 \u062f\u0633\u062a\u0647 \u0627\u0632 "
            "\u062f\u0633\u062a\u0648\u0631\u0647\u0627 "
            "\u0647\u0631\u06af\u0632 \u062a\u0623\u06cc\u06cc\u062f "
            "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
        )

    @property
    def refusal(self) -> str:
        """The bilingual refusal surfaced to the model, logs and UI."""
        return f"{self.message_en}\n{self.message_fa}"


_WRAPPER_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh"})


def _wrapped_payloads(text: ScanText) -> list[str]:
    """Extract inner commands handed to ``bash -c``-style wrappers."""
    payloads: list[str] = []
    for segment in _command_segments(text.tokens):
        verb = segment[0].rsplit("/", 1)[-1].lower()
        if verb in _WRAPPER_SHELLS and "-c" in segment[1:]:
            index = segment.index("-c", 1)
            if index + 1 < len(segment):
                payloads.append(" ".join(segment[index + 1:]))
    return payloads


def scan(command: str) -> BlockMatch | None:
    """Run every floor rule against *command*; the first match wins.

    Commands wrapped in ``bash -c`` (and siblings) are unwrapped and their
    payloads scanned too, so a wrapper never hides a floor event.

    Returns ``None`` when no rule fires. A ``None`` result never means the
    command is safe — it only means the floor does not own the decision, and
    the approval layers above must still judge it.
    """
    text = _build_scan_text(command)
    views = [text]
    views.extend(_build_scan_text(payload) for payload in _wrapped_payloads(text))
    for view in views:
        for rule in RULES:
            evidence = rule.detect(view)
            if evidence is not None:
                return BlockMatch(rule=rule, evidence=evidence)
    return None


def floor_refusal(command: str) -> str | None:
    """The bilingual refusal text for *command*, or ``None`` when unblocked."""
    match = scan(command)
    return match.refusal if match is not None else None
