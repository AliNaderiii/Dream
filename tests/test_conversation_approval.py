from __future__ import annotations

import tempfile
import threading
import time

from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore


def test_agent_dangerous_tool_waits_for_bridge_approval():
    base = tempfile.mktemp()
    methods = BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=f"{base}.json",
        sessions_db_path=f"{base}.db",
        providers_path=f"{base}.providers.json",
        default_provider="echo",
    )
    session_id = methods.session_create({})["session_id"]
    policy = methods.sessions[session_id].dream.approval_policy
    outcome: list[tuple[bool, str]] = []
    worker = threading.Thread(
        target=lambda: outcome.append(policy.allows("send_email", {"to": "owner@example.com"}))
    )
    worker.start()
    for _ in range(100):
        pending = methods.approval_list({})["approvals"]
        if pending:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("dangerous agent tool did not enter the approval queue")

    result = methods.approval_resolve(
        {"approval_id": pending[0]["approval_id"], "decision": "allow"}
    )
    worker.join(timeout=1)
    assert result["status"] == "approved"
    assert outcome and outcome[0][0] is True
    methods.shutdown()
