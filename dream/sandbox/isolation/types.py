"""Domain models and data structures for Sandbox Micro-Isolation and Syscall Filtering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class SyscallPolicy(str, Enum):
    """Access policy defining permitted syscall categories."""

    STRICT_READONLY = "strict_readonly"        # No write, no network, compute only
    COMPUTE_ONLY = "compute_only"              # Memory and math operations only
    PERMISSIVE_WORKSPACE = "permissive_workspace"  # Workspace read/write, no network
    DENY_ALL_UNSAFE = "deny_all_unsafe"        # Block ptrace, mount, kill, raw sockets


class IsolationLevel(str, Enum):
    """Enforcement mechanism for process sandboxing."""

    PROCESS_SECCOMP = "process_seccomp"  # Kernel-level syscall filter
    WASM_SANDBOX = "wasm_sandbox"        # Virtual memory WASM runtime
    CONTAINER_ROOTLESS = "container_rootless"  # OCI rootless container
    VIRTUAL_MACHINE = "virtual_machine"  # MicroVM / gVisor


@dataclass(slots=True)
class ResourceQuota:
    """Hard upper bounds on compute, memory, and output consumption."""

    max_cpu_time_sec: float = 10.0
    max_memory_mb: int = 256
    max_output_bytes: int = 1048576  # 1 MB
    max_processes: int = 1
    max_open_files: int = 16


@dataclass(slots=True)
class IsolationExecutionResult:
    """Detailed execution telemetry and security violation report."""

    execution_id: str
    isolation_level: IsolationLevel
    policy: SyscallPolicy
    exit_code: int
    stdout: str
    stderr: str
    syscalls_blocked: list[str] = field(default_factory=list)
    cpu_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    security_violations: list[str] = field(default_factory=list)
    success: bool = True
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "execution_id": self.execution_id,
            "isolation_level": self.isolation_level.value,
            "policy": self.policy.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "syscalls_blocked": self.syscalls_blocked,
            "cpu_time_ms": round(self.cpu_time_ms, 2),
            "memory_used_mb": round(self.memory_used_mb, 2),
            "security_violations": self.security_violations,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class IsolationProfile:
    """Security profile defining blocked syscall names and safety checks."""

    name: str
    policy: SyscallPolicy
    blocked_syscalls: tuple[str, ...]
    allow_network: bool = False
    allow_fork: bool = False
    allow_raw_sockets: bool = False

    @classmethod
    def strict(cls) -> IsolationProfile:
        """Create strict zero-trust profile."""
        return cls(
            name="strict_zero_trust",
            policy=SyscallPolicy.STRICT_READONLY,
            blocked_syscalls=(
                "ptrace", "mount", "umount", "chroot", "kill", "tkill",
                "socket", "connect", "bind", "listen", "accept",
                "clone", "fork", "vfork", "execve", "reboot",
            ),
            allow_network=False,
            allow_fork=False,
            allow_raw_sockets=False,
        )
