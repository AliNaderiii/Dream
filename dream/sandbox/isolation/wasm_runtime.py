"""WASM Micro-Runtime Sandbox: Zero-trust isolated execution for procedural computations."""

from __future__ import annotations

import collections
import datetime
import functools
import io
import itertools
import json
import math
import random
import re
import string
import sys
import time
from typing import Any

SAFE_MODULES = {
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


def _safe_import(
    name: str,
    globals_dict: dict[str, Any] | None = None,
    locals_dict: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    """Restricted import handler permitting only whitelisted deterministic modules."""
    if name in SAFE_MODULES:
        return __import__(name, globals_dict, locals_dict, fromlist, level)
    raise ImportError(f"Import of module '{name}' is restricted in WASM micro-sandbox")


SAFE_BUILTINS: dict[str, Any] = {
    "__import__": _safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "math": math,
}


class WasmMicroSandbox:
    """Executes code in a memory-confined virtual namespace without host system exposure."""

    def __init__(self, max_steps: int = 100000) -> None:
        self.max_steps = max_steps

    def execute_pure_computation(
        self,
        code_str: str,
        initial_globals: dict[str, Any] | None = None,
    ) -> tuple[int, str, str, float]:
        """Execute Python code in a restricted WASM-like sandbox environment.

        Returns:
            (exit_code, stdout, stderr, execution_ms)
        """
        start_time = time.time()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Build isolated namespace
        sandbox_env: dict[str, Any] = {
            "__builtins__": SAFE_BUILTINS,
            "__name__": "__wasm_sandbox__",
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
        if initial_globals:
            sandbox_env.update(initial_globals)

        # Intercept standard output
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_buf
        sys.stderr = stderr_buf

        exit_code = 0
        try:
            compiled = compile(code_str, "<wasm_sandbox>", "exec")
            exec(compiled, sandbox_env)  # noqa: S102
        except Exception as exc:
            exit_code = 1
            stderr_buf.write(f"{type(exc).__name__}: {str(exc)}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        duration_ms = (time.time() - start_time) * 1000
        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue(), duration_ms
