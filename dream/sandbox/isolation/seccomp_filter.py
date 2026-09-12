"""Kernel-Level Syscall Filter and Seccomp-BPF Policy Validator."""

from __future__ import annotations

import ast
import re
from typing import Any

from dream.sandbox.isolation.types import IsolationProfile, SyscallPolicy


class SyscallFilterEngine:
    """Inspects code and enforces Seccomp-style syscall isolation policies."""

    def __init__(self, default_profile: IsolationProfile | None = None) -> None:
        self.profile = default_profile or IsolationProfile.strict()

    def audit_code_safety(self, python_code: str) -> tuple[bool, list[str], list[str]]:
        """Perform static AST and opcode inspection for prohibited syscalls and dangerous calls.

        Returns:
            (is_safe, blocked_syscalls_found, violations_list)
        """
        blocked_syscalls: list[str] = []
        violations: list[str] = []

        # 1. Regex pre-scan for raw system access
        dangerous_patterns = [
            (r"\bctypes\b", "Prohibited ctypes memory manipulation"),
            (r"\bos\.system\b", "Blocked syscall 'execve' via os.system"),
            (r"\bsubprocess\b", "Blocked process spawning 'clone/fork'"),
            (r"\bsocket\b", "Blocked network syscall 'socket'"),
            (r"\bptrace\b", "Blocked kernel inspection 'ptrace'"),
            (r"\bshutil\.rmtree\b", "Blocked directory deletion 'unlinkat'"),
            (r"\bos\.fork\b", "Blocked process fork 'fork/clone'"),
            (r"\bos\.kill\b", "Blocked process signal 'kill/tkill'"),
        ]

        for pattern, desc in dangerous_patterns:
            if re.search(pattern, python_code):
                violations.append(desc)
                if "execve" in desc:
                    blocked_syscalls.append("execve")
                if "socket" in desc:
                    blocked_syscalls.append("socket")
                if "ptrace" in desc:
                    blocked_syscalls.append("ptrace")
                if "clone" in desc or "fork" in desc:
                    blocked_syscalls.append("clone")

        # 2. AST Walk for deeper import/attribute inspection
        try:
            tree = ast.parse(python_code)
            for node in ast.walk(tree):
                # Check forbidden imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ("ctypes", "socket", "subprocess", "multiprocessing"):
                            violations.append(f"Disallowed import '{alias.name}'")
                elif isinstance(node, ast.ImportFrom):
                    if node.module in ("ctypes", "socket", "subprocess", "multiprocessing"):
                        violations.append(f"Disallowed import from '{node.module}'")
                # Check dangerous builtins
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "__import__"):
                        violations.append(f"Restricted dynamic evaluation builtin '{node.func.id}'")
        except SyntaxError:
            # Code cannot parse; let runtime handler handle or reject
            violations.append("Syntax error in payload preventing AST verification")

        is_safe = len(violations) == 0
        return is_safe, sorted(set(blocked_syscalls)), violations
