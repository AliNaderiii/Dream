#!/usr/bin/env python3
"""Repeatable diagnostic for silent tool failures in Dream's memory loop.

Sends one fixed Persian sentence stating a durable fact through a real Dream
instance against a temporary database, then reports exactly what happened:

    python tools/memory_probe.py --backend ollama

Symptom under investigation: the model replies «ذخیره شد» (stored) while
``/mems`` shows nothing. Two causes produce identical symptoms — the model
never emits a tool call, or the call fails and the failure is narrated as
success. The verdict line distinguishes them. An earlier round of this
investigation kept its scripts locally and they were lost, forcing the
problem to be diagnosed twice; this probe is committed so that never happens
again.

Exit status: 0 when a memory was stored, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# When executed as ``python tools/memory_probe.py``, the interpreter puts
# tools/ on sys.path rather than the repository root, so make the root
# importable before importing Dream. (E402 waived for this file in ruff.)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dream.agent import Dream, build_backend
from dream.memory import MemoryStore

# One fixed sentence stating two durable facts; repetition removes the
# "maybe the model just chose differently today" variable from a diagnosis.
SENTENCE = "من روی یک استارتاپ فین‌تک کار می‌کنم و پایتون زبان اصلی‌ام است."

RESULT_SNIPPET_LIMIT = 200


@dataclass(slots=True)
class ProbeReport:
    """Everything the probe observed, plus the one-line verdict."""

    backend_label: str
    sentence: str
    reply: str
    tool_calls: list[dict[str, Any]]
    memories_after: int
    verdict: str

    @property
    def ok(self) -> bool:
        return self.verdict.startswith("OK")

    def render(self) -> str:
        """Human-readable transcript: calls, arguments, results, verdict."""
        lines = [
            f"[probe] backend: {self.backend_label}",
            f"[probe] input: {self.sentence}",
            f"[probe] reply: {self.reply}",
        ]
        if not self.tool_calls:
            lines.append("[probe] tool calls: none")
        else:
            lines.append(f"[probe] tool calls: {len(self.tool_calls)}")
            for index, call in enumerate(self.tool_calls, start=1):
                lines.append(f"[probe] #{index}: {call.get('name')}")
                arguments = json.dumps(call.get("arguments", {}), ensure_ascii=False)
                lines.append(f"[probe]   arguments: {arguments}")
                lines.append(f"[probe]   allowed: {call.get('allowed')}")
                lines.append(f"[probe]   result: {call.get('result')}")
        lines.append(f"[probe] memories in store after turn: {self.memories_after}")
        lines.append(f"[probe] verdict: {self.verdict}")
        return "\n".join(lines)


def _call_failed(result: str) -> bool:
    """Classify a recorded call result as failed.

    Kept independent of the product code it inspects: a diagnostic that
    reuses the code under investigation cannot detect that code's bugs.
    """
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return True
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("blocked")) or payload.get("status") == "error" or "error" in payload


def _verdict(calls: list[dict[str, Any]], memories_after: int) -> str:
    """Name the failure mode in one line, or confirm success."""
    if not calls:
        return (
            "FAIL: no tool call emitted - the model answered in prose, "
            "so nothing could have been stored"
        )
    failures = [call for call in calls if _call_failed(str(call.get("result", "")))]
    if failures:
        failing = failures[0]
        snippet = str(failing.get("result", ""))[:RESULT_SNIPPET_LIMIT]
        return f"FAIL: tool call failed - {failing.get('name')}: {snippet}"
    if memories_after > 0:
        return f"OK: memory stored successfully - {memories_after} memories in the store"
    names = ", ".join(str(call.get("name")) for call in calls)
    return f"FAIL: no memory stored - tool calls succeeded ({names}) but none wrote a memory"


def run_probe(backend: Any, sentence: str = SENTENCE) -> ProbeReport:
    """Run one fact-bearing sentence through a fresh Dream and temp database.

    Accepts any chat backend, so tests can pass an offline or scripted one
    while the CLI builds a real provider from ``--backend``.
    """
    label = f"{type(backend).__name__}({getattr(backend, 'model', '-')})"
    with tempfile.TemporaryDirectory() as directory:
        with MemoryStore(str(Path(directory) / "probe.db")) as store:
            turn = Dream(store, backend).run(sentence)
            memories_after = len(store.all())
    tool_calls = list(turn.tool_calls)
    return ProbeReport(
        backend_label=label,
        sentence=sentence,
        reply=turn.reply,
        tool_calls=tool_calls,
        memories_after=memories_after,
        verdict=_verdict(tool_calls, memories_after),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe whether Dream actually stores a stated fact in memory"
    )
    parser.add_argument("--backend", choices=("echo", "openai", "ollama"), default="ollama")
    parser.add_argument(
        "--sentence",
        default=SENTENCE,
        help="Fact-bearing sentence to send (defaults to the reported Persian repro)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_probe(build_backend(args.backend), sentence=args.sentence)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
