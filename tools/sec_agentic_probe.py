"""Independent, offline probe of the P6 agentic security layer (L9).

The audit (``tools/security_audit.py``) is the pass/fail alarm. This is
the diagnostic an owner runs when they want to *see* what the layer does
to a specific payload, plan, claim, or endpoint — one refusal at a time,
in plain text, with no network and no Docker.

Usage::

    python tools/sec_agentic_probe.py                 # the full walkthrough
    python tools/sec_agentic_probe.py code  "<program>"
    python tools/sec_agentic_probe.py data  "<cell text>"
    python tools/sec_agentic_probe.py claim "<prose>" 23.4 105
    python tools/sec_agentic_probe.py probe ollama http://127.0.0.1:11434/v1

Exit code is 0 whenever the probe itself ran; it is a lens, not a gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dream.security.agentcode import SandboxPolicy, preflight_code  # noqa: E402
from dream.security.authenticity import verify_claims  # noqa: E402
from dream.security.codegrounding import frame_as_data, scan_data_payload  # noqa: E402
from dream.security.planpolicy import (  # noqa: E402
    DEGRADED_GRANTS,
    EXPENSIVE_ACTIONS,
    PlanGate,
)
from dream.security.providergateway import ScopedTokenStore, probe_runtime  # noqa: E402


def _rule(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def probe_code(program: str) -> None:
    _rule("L9-A sandbox policy")
    policy = SandboxPolicy()
    print(
        f"policy: timeout={policy.timeout_seconds}s memory={policy.memory_mb}MB "
        f"cpu={policy.cpu_count} pids={policy.pids_limit} "
        f"network={policy.network_enabled} output_cap={policy.max_output_bytes}B"
    )
    refusal = preflight_code(program)
    if refusal is None:
        print("verdict: ALLOWED to reach the container (the host still never runs it)")
    else:
        print(f"verdict: REFUSED [{refusal.code}]")
        print(refusal.message())


def probe_data(cell: str) -> None:
    _rule("L9-B codegen grounding")
    report = scan_data_payload(cell)
    if report.safe:
        print("verdict: SAFE — framed as data:")
        print(frame_as_data(cell, label="probe"))
    else:
        print(f"verdict: REJECTED — findings={list(report.findings)} l5={list(report.l5_findings)}")
        print(report.reason_en)
        print(report.reason_fa)


def probe_plan() -> None:
    _rule("L9-C plan gate")
    steps = [{"index": 1, "title": "read schema"}, {"index": 2, "title": "run analysis"}]
    print(f"expensive actions : {sorted(EXPENSIVE_ACTIONS)}")
    print(f"degraded grants   : {sorted(DEGRADED_GRANTS)}")

    gate = PlanGate()
    refusal = gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=steps)
    print(f"unapproved run    : {refusal.code if refusal else 'ALLOWED'}")
    gate.request_approval(plan_id="p", kind="dataqa", steps=steps, approve=lambda _payload: True)
    ok = gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=steps)
    print(f"approved run      : {ok.code if ok else 'ALLOWED'}")
    mutated = steps + [{"index": 3, "title": "upload"}]
    swap = gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=mutated)
    print(f"plan swapped      : {swap.code if swap else 'ALLOWED'}")

    cron = PlanGate(context="cron")
    degraded = cron.check_action(
        action="code_execution", plan_id="p", kind="research", steps=steps
    )
    print(f"cron run          : {degraded.code if degraded else 'ALLOWED'}")


def probe_claim(prose: str, values: list[float]) -> None:
    _rule("L9-D claim verification")
    report = verify_claims(prose, values)
    print(f"computed values : {values}")
    print(f"numbers in prose: {list(report.checked)}")
    if report.grounded:
        print("verdict: GROUNDED")
    else:
        print("verdict: REFUSED")
        print(report.reason_en)
        print(report.reason_fa)


def probe_gateway(runtime_id: str = "ollama", endpoint: str | None = None) -> None:
    _rule("L9-E provider gateway")
    store = ScopedTokenStore()
    secret, record = store.issue("web_search", "read", label="probe")
    print(f"minted grant    : tool={record.tool} scope={record.scope} id={record.token_id}")
    print(f"snapshot        : {store.snapshot()}")
    print(f"secret in dump  : {secret in repr(store.snapshot())}")
    ok, why = store.verify(secret, tool="image")
    print(f"cross-tool use  : allowed={ok} reason={why.code if why else '-'}")

    result = probe_runtime(runtime_id, endpoint=endpoint)
    if result.ok:
        print(f"probe {runtime_id}: ok status={result.status} latency={result.latency_ms}ms")
    else:
        code = result.refusal.code if result.refusal else "unknown"
        print(f"probe {runtime_id}: refused/unreachable [{code}]")
    print(f"headers sent    : {result.headers_sent}")


def walkthrough() -> None:
    probe_code("import os\nos.system('id')\n")
    probe_code("import pandas as pd\nprint(pd.Series([1, 2]).mean())\n")
    probe_data("```python\nos.system('id')\n```")
    # «فروش سه‌ماههٔ اول در استان اصفهان»
    probe_data(
        "\u0641\u0631\u0648\u0634 \u0633\u0647\u200c\u0645\u0627\u0647\u0647\u0654 "
        "\u0627\u0648\u0644 \u062f\u0631 \u0627\u0633\u062a\u0627\u0646 "
        "\u0627\u0635\u0641\u0647\u0627\u0646"
    )
    probe_plan()
    probe_claim("Revenue grew by 42.7% this quarter.", [12.5, 3.0])
    probe_claim("Revenue grew by 23.4% this quarter.", [23.404])
    probe_gateway()


def main(argv: list[str]) -> int:
    if len(argv) <= 1:
        walkthrough()
        return 0
    command = argv[1]
    if command == "code" and len(argv) > 2:
        probe_code(argv[2])
    elif command == "data" and len(argv) > 2:
        probe_data(argv[2])
    elif command == "plan":
        probe_plan()
    elif command == "claim" and len(argv) > 2:
        values: list[float] = []
        for raw in argv[3:]:
            try:
                values.append(float(raw))
            except ValueError:
                print(f"skipping non-numeric evidence {raw!r}")
        probe_claim(argv[2], values)
    elif command == "probe":
        probe_gateway(argv[2] if len(argv) > 2 else "ollama", argv[3] if len(argv) > 3 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
