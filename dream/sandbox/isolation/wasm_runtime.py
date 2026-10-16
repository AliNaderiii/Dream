"""Restricted-execution micro-runtime — permanently disabled (MASTER-P0).

**This module no longer executes anything, and it never was what its name said.**

The previous implementation ran ``exec(compile(code))`` *in the Dream sidecar
process* with a hand-written ``__builtins__`` dictionary. That is a restricted
interpreter, not an isolation boundary: Python's object graph walks straight out
of any such dictionary (``(1).__class__.__bases__[0].__subclasses__()``,
``getattr``, ``__globals__``, generator frames), so the payload kept the full
authority of the sidecar. Calling it a "WASM micro-runtime" or a "seccomp
boundary" overstated the guarantee, which the MASTER-P0 brief forbids: a
heuristic must not be described as an OS sandbox, and claims must be backed by
evidence.

None of that was reachable from the product (no bridge method, no entry in the
tool ``REGISTRY``, no slash wiring), but unreachable-by-accident is not a
control, so the execution path is gone and the runtime fails closed.

Real isolation lives in :mod:`dream.security.codeexec` /
:mod:`dream.docker_sandbox` and is documented in
``docs/security/code-execution.md``.
"""

from __future__ import annotations

import collections
import datetime
import functools
import itertools
import json
import math
import random
import re
import string
from typing import Any

#: Modules the *analysis-hint* allowlist still names. Retained so existing
#: callers can inspect what the old runtime claimed to permit; nothing imports
#: them on behalf of a payload any more.
SAFE_MODULES: dict[str, Any] = {
    "math": math,
    "json": json,
    "re": re,
    "datetime": datetime,
    "itertools": itertools,
    "collections": collections,
    "functools": functools,
    "random": random,
    "string": string,
}

#: Refusal text, bilingual like the rest of Dream's fail-closed answers.
EXECUTION_DISABLED_EN = (
    "unavailable: this micro-runtime does not execute code; a restricted "
    "interpreter is not an isolation boundary"
)
EXECUTION_DISABLED_FA = (
    "در دسترس نیست: این ریز-اجراکننده کدی اجرا نمی‌کند؛ مفسر محدودشده مرز "
    "ایزولاسیون نیست"
)

#: Exit code used by the old policy denial path (kept for result continuity).
_POLICY_EXIT_CODE = 126


class WasmMicroSandbox:
    """A non-executing placeholder that reports its own unavailability.

    :attr:`available` is the field callers must branch on. It is ``False`` by
    construction and there is no setter, so no configuration can turn this back
    into a host interpreter.
    """

    #: Always False. There is no supported way to make this True.
    available: bool = False

    def __init__(self, max_steps: int = 100000) -> None:
        del max_steps  # no execution, so nothing to step-count

    def execute_pure_computation(
        self,
        code_str: str,
        initial_globals: dict[str, Any] | None = None,
    ) -> tuple[int, str, str, float]:
        """Refuse to execute *code_str*.

        Returns ``(exit_code, stdout, stderr, execution_ms)`` with
        ``exit_code == 126`` and the refusal in ``stderr``, matching the shape
        the old policy-denial path used so callers see a structured refusal
        rather than an exception.
        """
        del code_str, initial_globals
        return _POLICY_EXIT_CODE, "", f"{EXECUTION_DISABLED_EN}\n{EXECUTION_DISABLED_FA}", 0.0


__all__ = [
    "EXECUTION_DISABLED_EN",
    "EXECUTION_DISABLED_FA",
    "SAFE_MODULES",
    "WasmMicroSandbox",
]
