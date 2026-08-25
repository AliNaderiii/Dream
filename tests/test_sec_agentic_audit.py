"""P6 — the audit alarm must actually be wired to the new layers.

A smoke alarm that only ever answers "clean" is decoration. Every check
in this file breaks one L9 control in a subprocess and asserts the audit
turns red and names the layer. If a future refactor silently drops a
control, one of these sabotage runs stops failing and this file fails
instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT = REPO_ROOT / "tools" / "security_audit.py"

_RUNNER = """
import runpy
import sys

{sabotage}

sys.argv = ['security_audit.py']
try:
    runpy.run_path({audit!r}, run_name='__main__')
except SystemExit as exc:
    raise SystemExit(exc.code)
"""


def _run_audit(sabotage: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "sabotage_runner.py"
    script.write_text(
        _RUNNER.format(sabotage=sabotage, audit=str(AUDIT)), encoding="utf-8"
    )
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


# --------------------------------------------------------------------------- #
# The clean run
# --------------------------------------------------------------------------- #


def test_the_audit_is_clean_on_this_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(AUDIT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AUDIT CLEAN" in result.stdout


def test_the_audit_covers_every_new_layer() -> None:
    result = subprocess.run(
        [sys.executable, str(AUDIT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    for layer in ("L9-A", "L9-B", "L9-C", "L9-D", "L9-E"):
        assert layer in result.stdout, f"the audit never exercises {layer}"


# --------------------------------------------------------------------------- #
# Sabotage: every L9 control, broken one at a time
# --------------------------------------------------------------------------- #

SABOTAGE = {
    "L9-A import allowlist disabled": (
        "import dream.security.agentcode as m\n"
        "m.preflight_code = lambda code, **kw: None\n"
    ),
    "L9-A docker-absence no longer refuses": (
        "import dream.security.agentcode as m\n"
        "_orig = m.run_agent_code\n"
        "async def _lax(code, **kw):\n"
        "    return m.AgentCodeResult(stdout='ran on the host', return_code=0)\n"
        "m.run_agent_code = _lax\n"
    ),
    "L9-A path confinement removed": (
        "import dream.security.agentcode as m\n"
        "m.confine_path = lambda root, candidate: candidate\n"
    ),
    "L9-A output truncation removed": (
        "import dream.security.agentcode as m\n"
        "m.truncate_output = lambda text, limit: (text, False)\n"
    ),
    "L9-B codegen scanner disabled": (
        "import dream.security.codegrounding as m\n"
        "m.scan_data_payload = lambda text: m.GroundingReport(safe=True)\n"
    ),
    "L9-B data framing loses its banner": (
        "import dream.security.codegrounding as m\n"
        "m.frame_as_data = lambda text, label='x': str(text)\n"
    ),
    "L9-B literals become raw interpolation": (
        "import dream.security.codegrounding as m\n"
        "m.as_code_literal = lambda value: str(value)\n"
    ),
    "L9-C plan gate always allows": (
        "import dream.security.planpolicy as m\n"
        "m.PlanGate.check_action = lambda self, **kw: None\n"
    ),
    "L9-C autonomous sessions can mint approval": (
        "import dream.security.planpolicy as m\n"
        "m.AUTONOMOUS_CONTEXTS = frozenset()\n"
    ),
    "L9-C the approval throttle is removed": (
        "import dream.security.planpolicy as m\n"
        "m.ApprovalAttemptLimiter.allow = lambda self, subject, now=None: True\n"
    ),
    "L9-C expensive actions are reclassified as cheap": (
        "import dream.security.planpolicy as m\n"
        "m.EXPENSIVE_ACTIONS = frozenset()\n"
        "m.DEGRADED_GRANTS = m.DEGRADED_GRANTS | {'code_execution'}\n"
    ),
    "L9-D claim verification always passes": (
        "import dream.security.authenticity as m\n"
        "m.verify_claims = lambda text, values, **kw: m.ClaimReport(grounded=True)\n"
    ),
    "L9-D artifact seals are never checked": (
        "import dream.security.authenticity as m\n"
        "m.verify_artifact = lambda seal: (True, 'ok')\n"
    ),
    "L9-D run fingerprints ignore the code": (
        "import dream.security.authenticity as m\n"
        "m.RunFingerprint.run_hash = property(lambda self: 'constant')\n"
    ),
    "L9-E tokens stop being tool-scoped": (
        "import dream.security.providergateway as m\n"
        "m.ScopedTokenStore.verify = lambda self, secret, *, tool, scope='read', now=None: (\n"
        "    True, None\n"
        ")\n"
    ),
    "L9-E global grants are allowed": (
        "import dream.security.providergateway as m\n"
        "_orig = m.mint_token\n"
        "def _lax(tool, scope='read', **kw):\n"
        "    return _orig('web_search', 'read', **kw)\n"
        "m.mint_token = _lax\n"
        "m.ScopedTokenStore.issue = (\n"
        "    lambda self, tool, scope='read', **kw: _orig('web_search', 'read', **kw)\n"
        ")\n"
    ),
    "L9-E probes accept any endpoint": (
        "import dream.security.providergateway as m\n"
        "m._endpoint_allowed = lambda runtime_id, endpoint, extra: True\n"
    ),
    "L9-E snapshots stop redacting": (
        "import dream.security.providergateway as m\n"
        "m.safe_snapshot = lambda payload: payload\n"
        "m.redact_headers = lambda headers: dict(headers or {})\n"
    ),
    "L9-E the gateway enables every tool": (
        "import dream.providerhubs.gateway as g\n"
        "g.ToolGateway.snapshot = lambda self: {\n"
        "    'enabled': True,\n"
        "    'tools': [\n"
        "        {'id': t, 'enabled': True}\n"
        "        for t in ('web_search', 'image', 'tts', 'browser')\n"
        "    ],\n"
        "}\n"
    ),
}


@pytest.mark.parametrize("name,sabotage", sorted(SABOTAGE.items()))
def test_the_audit_fails_when_a_control_breaks(
    name: str, sabotage: str, tmp_path: Path
) -> None:
    result = _run_audit(sabotage, tmp_path)
    assert result.returncode == 1, (
        f"sabotage {name!r} did not turn the audit red\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "AUDIT FAILED" in result.stdout
    layer = name.split()[0]
    assert f"[FINDING] {layer}" in result.stdout, (
        f"sabotage {name!r} was caught, but not by {layer}\n{result.stdout}"
    )


def test_the_baseline_layers_still_alarm(tmp_path: Path) -> None:
    # The pre-P6 alarm must keep working: this is the zero-regression check
    # for the eight-layer battery the new sections were appended to.
    result = _run_audit(
        "import dream.security.blocklist as bl\nbl.scan = lambda command: None\n", tmp_path
    )
    assert result.returncode == 1
    assert "[FINDING] L3" in result.stdout
