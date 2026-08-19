"""Offline-first diagnostics for a Dream installation."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable

from dream.agent import ApprovalPolicy, build_backend
from dream.memory import MemoryStore, normalize_fa
from dream.tools import REGISTRY, openai_schemas

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"

# Gloss of each FAIL line, shown only when the console can encode Persian.
_FAIL_FA: dict[str, str] = {
    "Python": "پایتون ۳٫۱۰ یا جدیدتر نصب کنید.",
    "SQLite FTS5": "SQLite با FTS5 در دسترس نیست؛ یک ساخت دارای FTS5 نصب کنید.",
    "Package and memory": "بسته یا حافظه درست کار نمی‌کند؛ مجوز پایگاه داده را بررسی کنید.",
    "Normalisation": "نرمال‌سازی فارسی و عربی هم‌خوان نیست.",
    "Tool registry": "رجیستری ابزار خالی است؛ Dream را دوباره نصب کنید.",
    "Approval gate": "ابزار خطرناک بدون تأیید اجازه داده شد؛ سیاست را اصلاح کنید.",
    "Live tool calling": "مدل ابزار را صدا نزد؛ مدل یا تنظیم --backend را بررسی کنید.",
}

_SUMMARY_FAIL_EN = "One or more checks failed. Follow the action named above, then rerun doctor."
_SUMMARY_FAIL_FA = (
    "یک یا چند بررسی ناموفق بود. کار نوشته‌شده در بالا را انجام دهید و دوباره doctor را اجرا کنید."
)
_CRASH_FA = "بررسی doctor شکست خورد. Dream را دوباره نصب کنید و doctor را اجرا کنید."

_OLLAMA_MISSING_EN = (
    "Ollama was not found on this computer.",
    "Dream needs Ollama to run a local model without a VPN or an API key.",
    f"Download and install Ollama from: {OLLAMA_DOWNLOAD_URL}",
    "Then open Ollama once so it is running, and double-click run.bat again.",
)
_OLLAMA_MISSING_FA = (
    "اولاما روی این رایانه پیدا نشد.",
    "برای اجرای مدل محلی بدون فیلترشکن یا کلید API به اولاما نیاز است.",
    f"اولاما را از این نشانی دانلود و نصب کنید: {OLLAMA_DOWNLOAD_URL}",
    "بعد از نصب، یک‌بار اولاما را باز کنید و دوباره run.bat را اجرا کنید.",
)


def _can_print_persian(stream: object | None = None) -> bool:
    """True when *stream* (default stdout) can encode a Persian letter."""
    target = stream if stream is not None else sys.stdout
    encoding = getattr(target, "encoding", None) or "ascii"
    try:
        "\u0633\u0644\u0627\u0645".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _report(name: str, passed: bool, detail: str, output: Callable[[str], None]) -> bool:
    line = f"{'PASS' if passed else 'FAIL'} {name}: {detail}"
    if not passed:
        fa = _FAIL_FA.get(name)
        if fa and _can_print_persian():
            line = f"{line}  |  {fa}"
    output(line)
    return passed


def _mask(value: str) -> str:
    """Return a recognisable but safe representation of a secret."""
    if not value:
        return "not configured"
    return "***" if len(value) < 8 else f"{value[:3]}\u2026{value[-2:]}"


def print_ollama_missing(output: Callable[[str], None] = print) -> None:
    """Print the no-VPN Ollama-missing message (English always; Persian if UTF-8)."""
    output("")
    for line in _OLLAMA_MISSING_EN:
        output(line)
    if _can_print_persian():
        output("")
        for line in _OLLAMA_MISSING_FA:
            output(line)
    output("")


def run_checks(backend: str | None = None, output: Callable[[str], None] = print) -> bool:
    """Run offline checks and optionally verify real model tool calling."""
    checks: list[bool] = []
    checks.append(
        _report("Python", sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", output)
    )
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE check_fts USING fts5(content)")
        connection.close()
        checks.append(_report("SQLite FTS5", True, "available", output))
    except sqlite3.Error:
        checks.append(
            _report("SQLite FTS5", False, "unavailable; install SQLite with FTS5 enabled", output)
        )
    try:
        with tempfile.TemporaryDirectory() as directory:
            with MemoryStore(f"{directory}/doctor.db") as store:
                written = store.remember("doctor round trip")
                read = store.get(written.id)
                ok = read is not None and read.content == "doctor round trip"
        checks.append(
            _report(
                "Package and memory",
                ok,
                "memory round-trip succeeded" if ok else "memory round-trip failed",
                output,
            )
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        checks.append(
            _report("Package and memory", False, f"{exc}; check database permissions", output)
        )
    normalized = normalize_fa("مي\u200cخواهم كتاب") == normalize_fa("می‌خواهم کتاب")
    checks.append(
        _report(
            "Normalisation",
            normalized,
            "Arabic and Persian forms agree" if normalized else "normalisation mismatch",
            output,
        )
    )
    registry_ok = bool(REGISTRY)
    checks.append(
        _report(
            "Tool registry",
            registry_ok,
            "tools registered" if registry_ok else "empty; reinstall Dream",
            output,
        )
    )
    blocked, reason = ApprovalPolicy().allows("run_shell", {"command": "echo doctor"})
    checks.append(
        _report(
            "Approval gate",
            not blocked,
            reason if not blocked else "dangerous tool was allowed; remove unsafe policy",
            output,
        )
    )

    if backend:
        checks.append(_live_tool_check(backend, output))
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        output(f"API key configured: {_mask(key)}")
    return all(checks)


def _live_tool_check(backend_name: str, output: Callable[[str], None]) -> bool:
    """Ask a configured provider for a tool call, not merely fluent text."""
    try:
        backend = build_backend(backend_name)
        response = backend.chat(
            [
                {
                    "role": "user",
                    "content": "Use the calculate tool to compute 2 + 2. Do not answer in text.",
                }
            ],
            tools=openai_schemas(),
        )
        calls = response.get("tool_calls", [])
        if calls:
            return _report(
                "Live tool calling", True, f"model requested {calls[0].get('name')}", output
            )
        detail = response.get("content", "no response")
        return _report(
            "Live tool calling",
            False,
            f"model did not invoke a tool ({detail}). Choose a tool-calling model "
            "or check --backend configuration.",
            output,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        detail = f"{exc}; verify backend URL, model, and API key."
        if backend_name == "ollama":
            detail = (
                f"{exc}; is Ollama running? If it is not installed, download it from "
                f"{OLLAMA_DOWNLOAD_URL}."
            )
        return _report("Live tool calling", False, detail, output)


def _print_failure_summary() -> None:
    print(_SUMMARY_FAIL_EN, file=sys.stderr)
    if _can_print_persian(sys.stderr):
        print(_SUMMARY_FAIL_FA, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether Dream is ready to run")
    parser.add_argument(
        "--backend", choices=("openai", "ollama"), help="Also test a live model's tool calling"
    )
    parser.add_argument(
        "--message",
        choices=("ollama-missing",),
        help="Print a named onboarding message and exit (used by run.bat)",
    )
    args = parser.parse_args(argv)
    if args.message == "ollama-missing":
        print_ollama_missing()
        return 1
    try:
        passed = run_checks(args.backend)
    except Exception as exc:  # Diagnostics must name recovery, not show a traceback.
        print(f"FAIL doctor: {exc}. Reinstall Dream and run doctor again.", file=sys.stderr)
        if _can_print_persian(sys.stderr):
            print(_CRASH_FA, file=sys.stderr)
        return 1
    if not passed:
        _print_failure_summary()
        return 1
    print("Dream is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
