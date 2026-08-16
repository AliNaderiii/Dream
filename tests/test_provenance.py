"""Tests for Provenance System: Data Model, Log Tracker, and Reproducibility."""

import json
import os

from dream.provenance.artifact import ArtifactManager
from dream.provenance.models import (
    GENESIS_PREV_HASH,
    FileSnapshot,
    ProvenanceRecord,
)
from dream.provenance.reproducibility import ReproducibilityExporter
from dream.provenance.tracker import ProvenanceTracker


def test_provenance_record_hash_sealing_and_verification():
    rec = ProvenanceRecord(
        record_id="prov_01",
        timestamp="2026-08-15T12:00:00Z",
        event_type="tool_call",
        agent_id="sess_01",
        payload={"tool_name": "calculate", "arguments": {"expression": "2+2"}, "result": 4},
        duration_ms=15,
    )
    rec.seal(GENESIS_PREV_HASH)
    assert rec.hash != ""
    assert rec.verify_hash() is True

    # Tampering check
    rec.payload["result"] = 5
    assert rec.verify_hash() is False


def test_provenance_tracker_append_and_chain_verification(tmp_path):
    log_dir = str(tmp_path / "prov_log")
    tracker = ProvenanceTracker(log_dir=log_dir)

    r1 = tracker.record(
        event_type="user_message",
        agent_id="sess_10",
        payload={"content": "Generate a report"},
    )
    assert r1.prev_hash == GENESIS_PREV_HASH

    r2 = tracker.record(
        event_type="tool_call",
        agent_id="sess_10",
        parent_record_id=r1.record_id,
        payload={"tool_name": "run_analysis", "arguments": {}},
    )
    assert r2.prev_hash == r1.hash

    r3 = tracker.record(
        event_type="model_response",
        agent_id="sess_10",
        parent_record_id=r2.record_id,
        payload={"reply": "Report generated successfully"},
        model_snapshot={"provider": "echo", "model": "echo-v1"},
    )
    assert r3.prev_hash == r2.hash

    # Verify chain
    verification = tracker.verify_chain()
    assert verification["valid"] is True
    assert verification["records_checked"] == 3
    assert verification["broken_at"] is None

    # Retrieve record by ID
    fetched = tracker.get(r2.record_id)
    assert fetched is not None
    assert fetched.record_id == r2.record_id
    assert fetched.payload["tool_name"] == "run_analysis"


def test_provenance_tamper_detection(tmp_path):
    log_dir = str(tmp_path / "tamper_log")
    tracker = ProvenanceTracker(log_dir=log_dir)

    tracker.record(event_type="session_create", agent_id="s1", payload={})
    r2 = tracker.record(event_type="tool_call", agent_id="s1", payload={"tool": "safe_tool"})
    tracker.record(event_type="agent_message", agent_id="s1", payload={})

    # Tamper with file on disk
    active_file = os.path.join(log_dir, "provenance.jsonl")
    with open(active_file, encoding="utf-8") as f:
        lines = f.readlines()

    # Modify second record's payload without updating hash
    tampered_data = json.loads(lines[1])
    tampered_data["payload"]["tool"] = "malicious_tool"
    lines[1] = json.dumps(tampered_data) + "\n"

    with open(active_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Fresh tracker verifying the tampered log
    fresh_tracker = ProvenanceTracker(log_dir=log_dir)
    res = fresh_tracker.verify_chain()
    assert res["valid"] is False
    assert res["broken_at"] == r2.record_id
    assert "Tampered record content" in res["error"]


def test_provenance_artifact_linking_and_sidecars(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fig_file = workspace / "chart.png"
    fig_file.write_bytes(b"\x89PNG\r\n\x1a\nfake_image_data")

    tracker = ProvenanceTracker(log_dir=str(workspace / "prov"))
    rec = tracker.record(
        event_type="file_write",
        agent_id="sess_analysis",
        payload={"path": "chart.png", "tool_name": "plot_chart"},
        model_snapshot={"provider": "openai", "model": "gpt-4o"},
        output_snapshot=[FileSnapshot.from_path(str(fig_file), str(workspace))],
    )

    art_mgr = ArtifactManager(tracker, base_dir=str(workspace))
    sidecar = art_mgr.link_artifact("chart.png", rec.record_id)
    assert sidecar["record_id"] == rec.record_id
    assert sidecar["tool_name"] == "plot_chart"

    # Sidecar file created on disk
    sidecar_path = workspace / "chart.png.provenance.json"
    assert sidecar_path.exists()

    # Query artifact
    art_info = art_mgr.get_artifact("chart.png")
    assert art_info is not None
    assert art_info["record_id"] == rec.record_id
    assert "plot_chart" in art_info["lineage_statement"]
    assert "gpt-4o" in art_info["lineage_statement"]


def test_provenance_reproducibility_export(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_file = workspace / "input.csv"
    data_file.write_text("x,y\n1,2\n3,4", encoding="utf-8")

    tracker = ProvenanceTracker(log_dir=str(workspace / "prov"))
    r1 = tracker.record(
        event_type="user_message",
        agent_id="sess_exp",
        payload={"message": "Process input.csv"},
    )
    tracker.record(
        event_type="tool_call",
        agent_id="sess_exp",
        parent_record_id=r1.record_id,
        payload={"tool_name": "process_csv", "arguments": {"file": "input.csv"}},
        input_snapshot=[FileSnapshot.from_path(str(data_file), str(workspace))],
        model_snapshot={"provider": "ollama", "model": "llama3"},
    )

    exporter = ReproducibilityExporter(tracker, base_dir=str(workspace))
    out_zip = workspace / "repro.zip"
    res = exporter.export(session_id="sess_exp", output_file=str(out_zip))

    assert res["records_count"] == 2
    assert out_zip.exists()
    assert out_zip.stat().st_size > 0
