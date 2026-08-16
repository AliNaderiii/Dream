"""Docker sandbox — isolated, secure code execution environment.

Provides the :class:`DockerSandbox` class for running Python, R, and shell
scripts inside ephemeral Docker containers with strict resource limits and
security hardening.

Docker is **not required** at import time. All methods raise
:class:`DockerUnavailableError` when the Docker daemon is unreachable, so
callers (including the bridge) can degrade gracefully.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Language(str, Enum):
    """Supported execution languages."""

    PYTHON = "python"
    R = "r"
    BASH = "bash"


class Kernel(str, Enum):
    """Jupyter kernel identifiers."""

    PYTHON3 = "python3"
    IR = "ir"


@dataclass
class ResourceLimits:
    """Resource constraints for a sandbox container."""

    cpu_count: float = 1.0  # CPU cores (fraction allowed)
    memory_mb: int = 2048  # memory limit in MB
    disk_mb: int = 1024  # disk limit in MB (via --storage-opt)
    network_enabled: bool = False  # network access (opt-in)
    timeout_seconds: int = 60  # max execution wall time
    pids_limit: int = 100  # max number of processes


@dataclass
class SandboxResult:
    """Result of a sandbox execution."""

    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    timed_out: bool = False
    output_files: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: str | None = None


class DockerUnavailableError(RuntimeError):
    """Raised when Docker daemon is not reachable."""


class SandboxTimeoutError(RuntimeError):
    """Raised when execution exceeds the configured timeout."""


class SandboxExecutionError(RuntimeError):
    """Raised when code execution fails inside the container."""


# ---------------------------------------------------------------------------
# DockerSandbox
# ---------------------------------------------------------------------------


class DockerSandbox:
    """Isolated execution environment using Docker containers.

    Usage::

        sandbox = DockerSandbox()
        result = await sandbox.run_code(
            code="print('hello')",
            language="python",
            workspace_path=Path("/tmp/work"),
            resource_limits=ResourceLimits(),
        )
        print(result.stdout)  # "hello\\n"

    Images are pulled on first use and cached. The sandbox auto-removes
    containers after execution unless ``keep_container`` is set.
    """

    #: Default images for each language.
    DEFAULT_IMAGES: dict[Language, str] = {
        Language.PYTHON: "python:3.12-slim",
        Language.R: "rocker/r-ver:4.4",
        Language.BASH: "alpine:3.19",
    }

    #: Extra packages pre-installed for Python images.
    PYTHON_BASE_PACKAGES: list[str] = [
        "numpy",
        "pandas",
        "matplotlib",
        "seaborn",
        "scikit-learn",
        "jupyter",
        "nbformat",
        "nbconvert",
    ]

    #: Extra packages pre-installed for R images.
    R_BASE_PACKAGES: list[str] = [
        "tidyverse",
        "rmarkdown",
        "repr",
        "IRkernel",
    ]

    def __init__(
        self,
        *,
        docker_host: str | None = None,
        data_dir: str | None = None,
        keep_containers: bool = False,
        auto_pull: bool = True,
    ) -> None:
        """Initialise the sandbox.

        Args:
            docker_host: Docker daemon socket (e.g. ``unix:///var/run/docker.sock``).
                Defaults to the ``DOCKER_HOST`` env var or the default Unix socket.
            data_dir: Directory for storing temporary workspace copies and images.
                Defaults to ``~/.dream/sandbox``.
            keep_containers: If ``True``, containers are not auto-removed after
                execution (useful for debugging).
            auto_pull: If ``True``, pull images automatically on first use.
        """
        self._docker_host = docker_host or os.environ.get("DOCKER_HOST")
        self._data_dir = Path(data_dir or os.path.expanduser("~/.dream/sandbox"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._keep_containers = keep_containers
        self._auto_pull = auto_pull
        self._pulled_images: set[str] = set()
        self._checked = False

        # Seccomp profile content (block unnecessary syscalls).
        self._seccomp_profile = self._build_seccomp_profile()

    # -- public API ------------------------------------------------------- #

    async def check_docker(self) -> dict[str, Any]:
        """Verify Docker daemon is reachable.

        Returns a status dict. Raises :class:`DockerUnavailableError` on failure.
        """
        try:
            info = await self._run_docker_cmd("info", ["--format", "{{json .}}"])
            parsed = json.loads(info)
            return {
                "available": True,
                "version": parsed.get("ServerVersion", "unknown"),
                "os": parsed.get("OperatingSystem", "unknown"),
                "containers_running": parsed.get("ContainersRunning", 0),
                "containers_total": parsed.get("Containers", 0),
                "images": parsed.get("Images", 0),
            }
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise DockerUnavailableError(
                f"Docker daemon is not reachable: {exc}"
            ) from exc

    async def check_available(self) -> bool:
        """Return ``True`` if Docker is reachable (no exception)."""
        try:
            await self.check_docker()
            return True
        except DockerUnavailableError:
            return False

    async def run_code(
        self,
        code: str,
        language: Literal["python", "r", "bash"] = "python",
        workspace_path: Path | None = None,
        resource_limits: ResourceLimits | None = None,
        *,
        env_vars: dict[str, str] | None = None,
        mount_workspace_read_write: bool = False,
        keep_container: bool | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        """Execute ``code`` inside a sandbox container.

        Args:
            code: Source code to execute.
            language: ``"python"``, ``"r"``, or ``"bash"``.
            workspace_path: Host directory to mount into the container. Creates
                a temporary workspace if ``None``.
            resource_limits: Resource constraints. Defaults to sane limits.
            env_vars: Extra environment variables for the container.
            mount_workspace_read_write: Mount workspace as read-write (default
                read-only) for approved tasks.
            keep_container: Override the instance-wide ``keep_containers``.
            timeout: Override the resource_limits timeout.

        Returns:
            :class:`SandboxResult` with captured output and extracted files.
        """
        limits = resource_limits or ResourceLimits()
        lang = Language(language)
        image = self.DEFAULT_IMAGES[lang]
        timeout_s = timeout if timeout is not None else limits.timeout_seconds
        keep = keep_container if keep_container is not None else self._keep_containers

        # Auto-pull image if needed.
        await self._ensure_image(image)

        # Prepare workspace.
        workspace = workspace_path or Path(tempfile.mkdtemp(prefix="dream-sandbox-"))
        created_temp = workspace_path is None
        try:
            if not workspace.exists():
                workspace.mkdir(parents=True, exist_ok=True)

            # Write code to a file inside the workspace.
            code_filename = self._code_filename(lang)
            code_path = workspace / code_filename
            code_path.write_text(code, encoding="utf-8")

            # Build the docker run command.
            result = await self._exec_in_container(
                image=image,
                language=lang,
                code_filename=code_filename,
                workspace=workspace,
                limits=limits,
                timeout_s=timeout_s,
                env_vars=env_vars,
                read_write=mount_workspace_read_write,
                keep=keep,
            )

            # Extract output files from the container.
            if result.return_code == 0 and not result.timed_out:
                result.output_files = await self._extract_output_files(
                    workspace, language
                )

            return result

        finally:
            if created_temp and not keep:
                self._cleanup_temp(workspace)

    async def run_notebook(
        self,
        notebook_path: Path | str,
        kernel: Literal["python3", "ir"] = "python3",
        timeout: int = 300,
        *,
        resource_limits: ResourceLimits | None = None,
    ) -> SandboxResult:
        """Execute a Jupyter notebook inside the sandbox.

        Uses ``jupyter nbconvert --execute`` for Python kernels or ``Rscript``
        with ``rmarkdown::render()`` for R.

        Args:
            notebook_path: Path to the ``.ipynb`` file.
            kernel: Kernel to use (``"python3"`` or ``"ir"``).
            timeout: Maximum execution time in seconds.
            resource_limits: Resource constraints.

        Returns:
            :class:`SandboxResult` with the executed notebook and output.
        """
        nb_path = Path(notebook_path)
        if not nb_path.exists():
            raise FileNotFoundError(f"Notebook not found: {nb_path}")

        limits = resource_limits or ResourceLimits()
        lang = Language.PYTHON if kernel == "python3" else Language.R
        image = self.DEFAULT_IMAGES[lang]
        await self._ensure_image(image)

        workspace = nb_path.parent
        code_filename = nb_path.name

        if kernel == "python3":
            # Execute via nbconvert.
            exec_cmd = (
                f"jupyter nbconvert --to notebook --execute "
                f"--ExecutePreprocessor.timeout={timeout} "
                f"--ExecutePreprocessor.kernel_name={kernel} "
                f"{code_filename} --output {code_filename}.executed"
            )
        else:
            # R kernel: use rmarkdown.
            exec_cmd = (
                "Rscript -e "
                f"\"rmarkdown::render('{code_filename}', "
                f"output_file='{code_filename}.executed.html')\""
            )

        result = await self._exec_in_container(
            image=image,
            language=lang,
            code_filename=code_filename,
            workspace=workspace,
            limits=limits,
            timeout_s=timeout,
            exec_command=exec_cmd,
        )

        if result.return_code == 0:
            result.output_files = await self._extract_output_files(workspace, language=lang)

        return result

    async def install_packages(
        self,
        packages: list[str],
        language: Literal["python", "r"] = "python",
        *,
        resource_limits: ResourceLimits | None = None,
    ) -> bool:
        """Install packages into the base image (creates a new layer).

        This builds a new image tagged ``dream-sandbox-{language}:custom``.

        Args:
            packages: Package names to install.
            language: ``"python"`` or ``"r"``.
            resource_limits: Resource constraints for the build.

        Returns:
            ``True`` if the build succeeded.

        Raises:
            SandboxExecutionError: If package installation fails.
        """
        limits = resource_limits or ResourceLimits(timeout_seconds=300)
        lang = Language(language)
        base_image = self.DEFAULT_IMAGES[lang]
        tag = f"dream-sandbox-{language}:custom"

        # Build a Dockerfile.
        if lang == Language.PYTHON:
            pip_args = " ".join(packages)
            dockerfile = (
                f"FROM {base_image}\n"
                f"RUN pip install --no-cache-dir {pip_args}\n"
            )
        else:
            r_args = " ".join(f"'{p}'" for p in packages)
            dockerfile = (
                f"FROM {base_image}\n"
                f"RUN Rscript -e \"install.packages(c({r_args}), repos='https://cloud.r-project.org/')\"\n"
            )

        # Write to a temp dir and build.
        build_dir = self._data_dir / "builds" / f"{language}-{uuid.uuid4().hex[:12]}"
        build_dir.mkdir(parents=True, exist_ok=True)
        try:
            (build_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
            cmd = ["build", "-t", tag, "-f", "Dockerfile", "."]
            stdout, stderr = await self._run_docker_cmd_with_output(
                cmd, cwd=str(build_dir), timeout=limits.timeout_seconds
            )
            # Update the default image for this language.
            self.DEFAULT_IMAGES[lang] = tag
            return True
        except subprocess.SubprocessError as exc:
            raise SandboxExecutionError(
                f"Package installation failed: {exc}"
            ) from exc
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)

    async def get_status(self) -> dict[str, Any]:
        """Return sandbox status: Docker availability, images cached, etc."""
        try:
            info = await self.check_docker()
        except DockerUnavailableError:
            return {
                "available": False,
                "docker": False,
                "error": "Docker daemon not reachable",
            }

        # Check which images are available.
        images_available: dict[str, bool] = {}
        for lang, img in self.DEFAULT_IMAGES.items():
            try:
                await self._run_docker_cmd("inspect", [img])
                images_available[lang.value] = True
            except subprocess.SubprocessError:
                images_available[lang.value] = False

        return {
            "available": True,
            "docker": info,
            "images_available": images_available,
            "default_images": {k.value: v for k, v in self.DEFAULT_IMAGES.items()},
            "keep_containers": self._keep_containers,
            "data_dir": str(self._data_dir),
        }

    # -- internals -------------------------------------------------------- #

    async def _ensure_image(self, image: str) -> None:
        """Pull the image if not already pulled/cached."""
        if image in self._pulled_images:
            return
        if not self._auto_pull:
            return
        try:
            # Check if the image exists locally.
            await self._run_docker_cmd("inspect", [image])
        except subprocess.SubprocessError:
            # Pull it.
            await self._run_docker_cmd("pull", [image], timeout=300)
        self._pulled_images.add(image)

    async def _exec_in_container(
        self,
        *,
        image: str,
        language: Language,
        code_filename: str,
        workspace: Path,
        limits: ResourceLimits,
        timeout_s: int,
        env_vars: dict[str, str] | None = None,
        read_write: bool = False,
        keep: bool = False,
        exec_command: str | None = None,
    ) -> SandboxResult:
        """Run code inside a container and capture output."""
        container_name = f"dream-sandbox-{uuid.uuid4().hex[:12]}"
        started_at = time.monotonic()
        result = SandboxResult()

        # Build the command.
        cmd = ["run", "--rm"] if not keep else ["run"]

        # Container name.
        cmd.extend(["--name", container_name])

        # Security hardening.
        cmd.extend([
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--read-only",
            "--memory-swap=0",  # disable swap
        ])

        # Resource limits.
        cmd.extend([f"--cpus={limits.cpu_count}"])
        cmd.extend([f"--memory={limits.memory_mb}m"])
        cmd.extend([f"--pids-limit={limits.pids_limit}"])
        if limits.disk_mb > 0:
            cmd.extend([f"--storage-opt=size={limits.disk_mb}m"])

        # Network: disabled by default.
        if not limits.network_enabled:
            cmd.append("--network=none")

        # Seccomp profile.
        seccomp_path = self._write_seccomp_profile()
        cmd.extend(["--security-opt", f"seccomp={seccomp_path}"])

        # User namespace remapping (root in container != root on host).
        cmd.append("--userns=remap:default")

        # Mount workspace.
        mount_mode = "rw" if read_write else "ro"
        cmd.extend(["-v", f"{workspace.resolve()}:/workspace:{mount_mode}"])
        cmd.extend(["-w", "/workspace"])

        # Environment variables.
        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Python-specific: set PYTHONUNBUFFERED.
        if language == Language.PYTHON:
            cmd.extend(["-e", "PYTHONUNBUFFERED=1"])

        # Image.
        cmd.append(image)

        # Execution command.
        if exec_command:
            cmd.extend(["/bin/sh", "-c", exec_command])
        else:
            cmd.extend(self._run_command(language, code_filename))

        try:
            stdout, stderr = await self._run_docker_cmd_with_output(
                cmd, timeout=timeout_s
            )
            result.stdout = stdout
            result.stderr = stderr
            result.return_code = 0
        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.stderr = f"Execution timed out after {timeout_s}s"
            result.return_code = -1
            # Force-kill the container.
            try:
                await self._run_docker_cmd("kill", [container_name], timeout=5)
            except subprocess.SubprocessError:
                pass
        except subprocess.CalledProcessError as exc:
            result.stdout = exc.stdout or ""
            result.stderr = exc.stderr or ""
            result.return_code = exc.returncode
        except FileNotFoundError as exc:
            raise DockerUnavailableError("Docker executable not found in PATH") from exc

        result.elapsed_seconds = round(time.monotonic() - started_at, 3)

        # Clean up the container if keep is True and it wasn't --rm.
        if keep:
            try:
                await self._run_docker_cmd("rm", ["-f", container_name], timeout=10)
            except subprocess.SubprocessError:
                pass

        return result

    async def _extract_output_files(
        self, workspace: Path, language: str
    ) -> list[str]:
        """Detect and collect output files (images, CSVs, etc.) from the workspace."""
        output_files: list[str] = []
        allowed_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf",
            ".csv", ".tsv", ".json", ".xlsx", ".html", ".ipynb",
            ".txt", ".md", ".rds", ".rdata",
        }

        for f in workspace.iterdir():
            if f.is_file() and f.suffix.lower() in allowed_extensions:
                # Copy to a persistent output directory.
                output_dir = self._data_dir / "outputs"
                output_dir.mkdir(parents=True, exist_ok=True)
                dest = output_dir / f.name
                # Avoid overwrites.
                counter = 1
                while dest.exists():
                    stem = f.stem
                    dest = output_dir / f"{stem}_{counter}{f.suffix}"
                    counter += 1
                shutil.copy2(f, dest)
                output_files.append(str(dest.resolve()))

        return output_files

    # -- helpers ---------------------------------------------------------- #

    @staticmethod
    def _code_filename(language: Language) -> str:
        """Return the filename for the code file based on language."""
        return {
            Language.PYTHON: "script.py",
            Language.R: "script.R",
            Language.BASH: "script.sh",
        }[language]

    @staticmethod
    def _run_command(language: Language, filename: str) -> list[str]:
        """Return the command to execute the code file."""
        commands = {
            Language.PYTHON: ["python3", filename],
            Language.R: ["Rscript", filename],
            Language.BASH: ["/bin/bash", filename],
        }
        return commands[language]

    @staticmethod
    def _build_seccomp_profile() -> dict[str, Any]:
        """Build a restrictive seccomp profile for the sandbox."""
        return {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
            "syscalls": [
                {
                    "names": [
                        "accept", "access", "arch_prctl", "bind", "brk",
                        "chdir", "chmod", "clock_getres", "clock_gettime",
                        "clock_nanosleep", "clone", "close", "connect",
                        "copy_file_range", "creat", "dup", "dup2", "dup3",
                        "epoll_create", "epoll_create1", "epoll_ctl",
                        "epoll_wait", "eventfd", "eventfd2", "execve",
                        "exit", "exit_group", "faccessat", "fchdir",
                        "fchmod", "fchmodat", "fchown", "fchownat",
                        "fcntl", "fdatasync", "fgetxattr", "flistxattr",
                        "flock", "fremovexattr", "fsync", "ftruncate",
                        "futex", "getcwd", "getdents", "getdents64",
                        "getegid", "geteuid", "getgid", "getgroups",
                        "getpeername", "getpgrp", "getpid", "getppid",
                        "getrandom", "getresgid", "getresuid", "getrlimit",
                        "getrusage", "getsockname", "getsockopt",
                        "gettid", "gettimeofday", "getuid", "getxattr",
                        "ioctl", "ipc", "listen", "lseek", "lstat",
                        "madvise", "mkdir", "mkdirat", "mlock",
                        "mlock2", "mlockall", "mmap", "mount", "mprotect",
                        "mremap", "munlock", "munlockall", "munmap",
                        "nanosleep", "newfstatat", "open", "openat",
                        "pause", "pipe", "pipe2", "poll", "ppoll",
                        "prctl", "pread64", "preadv", "pselect6",
                        "pwrite64", "pwritev", "read", "readlink",
                        "readlinkat", "readv", "recvfrom", "recvmsg",
                        "rename", "renameat", "rmdir", "rt_sigaction",
                        "rt_sigpending", "rt_sigprocmask",
                        "rt_sigqueueinfo", "rt_sigreturn",
                        "rt_sigsuspend", "rt_sigtimedwait",
                        "sched_getaffinity", "sched_getattr",
                        "sched_getparam", "sched_getscheduler",
                        "sched_yield", "seccomp", "select", "sendfile",
                        "sendmsg", "sendto", "set_robust_list",
                        "set_tid_address", "setgid", "setgroups",
                        "setitimer", "setpgid", "setresgid",
                        "setresuid", "setrlimit", "setsid",
                        "setsockopt", "sigaltstack", "socket",
                        "socketpair", "stat", "statx", "symlink",
                        "symlinkat", "sync", "syncfs", "sysinfo",
                        "tee", "time", "timer_create", "timer_delete",
                        "timer_getoverrun", "timer_gettime",
                        "timer_settime", "times", "truncate",
                        "umask", "uname", "unlink", "unlinkat",
                        "utime", "utimensat", "utimes", "wait4",
                        "waitid", "write", "writev",
                    ],
                    "action": "SCMP_ACT_ALLOW",
                },
            ],
        }

    def _write_seccomp_profile(self) -> str:
        """Write the seccomp profile to a temp file and return the path."""
        path = str(self._data_dir / "seccomp-profile.json")
        if not Path(path).exists():
            Path(path).write_text(
                json.dumps(self._seccomp_profile, indent=2), encoding="utf-8"
            )
        return path

    @staticmethod
    def _cleanup_temp(workspace: Path) -> None:
        """Remove a temporary workspace directory."""
        try:
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
        except OSError:
            pass

    async def _run_docker_cmd(
        self, sub_cmd: str, args: list[str], timeout: int = 60
    ) -> str:
        """Run a docker command and return stdout as a string."""
        stdout, _ = await self._run_docker_cmd_with_output(
            [sub_cmd, *args], timeout=timeout
        )
        return stdout

    async def _run_docker_cmd_with_output(
        self, cmd: list[str], timeout: int = 60, cwd: str | None = None
    ) -> tuple[str, str]:
        """Run docker with the given arguments and return (stdout, stderr)."""
        docker_cmd = ["docker"]
        if self._docker_host:
            docker_cmd.extend(["-H", self._docker_host])
        docker_cmd.extend(cmd)

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise subprocess.TimeoutExpired(
                cmd=" ".join(docker_cmd), timeout=timeout
            ) from exc

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode,
                cmd=" ".join(docker_cmd),
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
            )

        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )


__all__ = [
    "DockerSandbox",
    "DockerUnavailableError",
    "SandboxResult",
    "SandboxTimeoutError",
    "SandboxExecutionError",
    "ResourceLimits",
    "Language",
    "Kernel",
]