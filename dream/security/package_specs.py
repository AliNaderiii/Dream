"""Deliberately small package grammar; no optional runtime parser dependency.

Python: ASCII distribution name, optionally == a numeric-release version
with optional a/b/rc, post, dev and local suffixes. R: ASCII
letter followed by letters, digits or dots. No extras, markers, URLs or options.
At most 64 specs, each at most 128 characters. See code-execution.md.
"""

import re

_PYTHON = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
                     r"(?:==[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?"
                     r"(?:\.post[0-9]+)?(?:\.dev[0-9]+)?"
                     r"(?:\+[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)?)?", re.ASCII)
_R = re.compile(r"[A-Za-z][A-Za-z0-9.]*", re.ASCII)


def validate_packages(packages: object, language: object = "python") -> list[str]:
    """Reject untrusted input before any probe, directory, build or mutation."""
    if language not in ("python", "r"):
        raise ValueError("language must be python or r")
    if not isinstance(packages, list) or not 1 <= len(packages) <= 64:
        raise ValueError("packages must contain 1..64 strings")
    pattern = _PYTHON if language == "python" else _R
    for spec in packages:
        if not isinstance(spec, str) or not 1 <= len(spec) <= 128 or not pattern.fullmatch(spec):
            raise ValueError("unsupported package spec; use a name or Python name==version")
    return list(packages)
