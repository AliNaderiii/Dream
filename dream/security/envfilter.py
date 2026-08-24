"""Allowlist-filtered environments for MCP child processes (L6, SEC-G-14).

A stdio MCP server is a child process Dream launches on the owner's
machine. Before Stage C it inherited the ENTIRE parent environment —
provider API keys, gateway tokens, platform credentials. That was a leak:
one malicious ``env`` dump from the child exfiltrated everything.

The rule now: a child receives a small functional allowlist (PATH, HOME,
locale, temp dirs, shell basics) plus ONLY the variables the owner
explicitly mapped in the server's ``env`` config. Everything else stays
with Dream. The allowlist is intentionally boring: paths and locale, never
credentials. If a server needs a token, the owner maps it deliberately and
visibly.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

__all__ = ["CHILD_ENV_ALLOWLIST", "build_child_env"]

#: Case-normalized (upper) names a child process commonly needs to function.
#: Deliberately excludes anything secret-bearing: no *_KEY, no *_TOKEN,
#: no *_SECRET, no DREAM_* (gateway tokens, provider config), no
#: GITHUB/GH_*, no OPENAI/ANTHROPIC/GOOGLE/SLACK/TELEGRAM credentials.
CHILD_ENV_ALLOWLIST = frozenset(
    {
        # POSIX basics
        "PATH",
        "HOME",
        "SHELL",
        "USER",
        "LOGNAME",
        "TERM",
        "TZ",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        # Windows basics
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "OS",
        "NUMBER_OF_PROCESSORS",
        # Runtime hints children commonly need (never credentials)
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "PYTHONDONTWRITEBYTECODE",
        "VIRTUAL_ENV",
        "NODE_OPTIONS",
        "UV",
    }
)


def build_child_env(explicit: Mapping[str, str] | None) -> dict[str, str]:
    """The environment for one MCP child: allowlist + explicit mappings only.

    ``explicit`` is the server config's ``env`` map — the sole channel by
    which anything outside the allowlist reaches a child. Keys and values
    are stringified so a malformed config cannot smuggle objects through.
    """
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.upper() in CHILD_ENV_ALLOWLIST:
            env[key] = value
    for key in explicit or {}:
        env[str(key)] = str((explicit or {})[key])
    return env
