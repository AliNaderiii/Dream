"""P6 L9-D — artifact seals and ungrounded-claim rejection.

Two failures are in scope. A figure whose file changed after it was
sealed is no longer the figure the provenance record describes. A
sentence that quotes a number nothing computed is a fabrication, however
confident it sounds. Both must be caught offline, without a provenance
store present, and both refusals must be bilingual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dream.provenance import ArtifactManager, ProvenanceTracker
from dream.security.authenticity import (
    RunFingerprint,
    extract_numbers,
    seal_artifact,
    verify_artifact,
    verify_claims,
)


@pytest.fixture()
def figure(tmp_path: Path) -> Path:
    target = tmp_path / "chart.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n figure bytes")
    return target


@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    target = tmp_path / "sales.csv"
    target.write_text("region,revenue\nnorth,120\nsouth,90\n", encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# Run fingerprints
# --------------------------------------------------------------------------- #


def test_the_fingerprint_binds_code_data_and_run(dataset: Path) -> None:
    base = RunFingerprint.build(
        code="print('x')", inputs=[dataset], params={"bins": 10}, run_id="r1", tool="dataqa"
    )
    assert base.run_hash
    assert base.code_hash and base.params_hash
    assert base.data_hashes[0][0] == "sales.csv"


def test_changing_the_code_changes_the_run_hash(dataset: Path) -> None:
    a = RunFingerprint.build(code="print('a')", inputs=[dataset], run_id="r1")
    b = RunFingerprint.build(code="print('b')", inputs=[dataset], run_id="r1")
    assert a.run_hash != b.run_hash


def test_changing_the_data_changes_the_run_hash(dataset: Path) -> None:
    a = RunFingerprint.build(code="print('x')", inputs=[dataset], run_id="r1")
    dataset.write_text("region,revenue\nnorth,999\n", encoding="utf-8")
    b = RunFingerprint.build(code="print('x')", inputs=[dataset], run_id="r1")
    assert a.run_hash != b.run_hash


def test_changing_the_parameters_changes_the_run_hash(dataset: Path) -> None:
    a = RunFingerprint.build(code="x", inputs=[dataset], params={"bins": 10}, run_id="r1")
    b = RunFingerprint.build(code="x", inputs=[dataset], params={"bins": 20}, run_id="r1")
    assert a.run_hash != b.run_hash


def test_the_fingerprint_is_order_insensitive_over_inputs(tmp_path: Path) -> None:
    one = tmp_path / "a.csv"
    two = tmp_path / "b.csv"
    one.write_text("a", encoding="utf-8")
    two.write_text("b", encoding="utf-8")
    forward = RunFingerprint.build(code="x", inputs=[one, two], run_id="r")
    backward = RunFingerprint.build(code="x", inputs=[two, one], run_id="r")
    assert forward.run_hash == backward.run_hash


def test_an_unreadable_input_is_recorded_not_hidden(tmp_path: Path) -> None:
    missing = tmp_path / "gone.csv"
    fingerprint = RunFingerprint.build(code="x", inputs=[missing], run_id="r")
    assert fingerprint.data_hashes == (("gone.csv", "unreadable"),)


# --------------------------------------------------------------------------- #
# Artifact seals
# --------------------------------------------------------------------------- #


def test_a_sealed_artifact_verifies(figure: Path, dataset: Path) -> None:
    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    seal = seal_artifact(figure, fingerprint, kind="figure")
    ok, detail = verify_artifact(seal)
    assert ok, detail


def test_a_tampered_artifact_fails_its_seal(figure: Path, dataset: Path) -> None:
    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    seal = seal_artifact(figure, fingerprint, kind="figure")
    figure.write_bytes(b"\x89PNG different bytes entirely")
    ok, detail = verify_artifact(seal)
    assert not ok
    assert "changed" in detail
    assert any("\u0600" <= ch <= "\u06ff" for ch in detail)


def test_a_deleted_artifact_is_unverifiable_not_valid(figure: Path, dataset: Path) -> None:
    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    seal = seal_artifact(figure, fingerprint)
    figure.unlink()
    ok, detail = verify_artifact(seal)
    assert not ok and "unverifiable" in detail


def test_a_forged_seal_field_does_not_verify(figure: Path, dataset: Path) -> None:
    from dataclasses import replace

    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    seal = seal_artifact(figure, fingerprint)
    forged = replace(seal, run_hash="0" * 64)
    ok, detail = verify_artifact(forged)
    assert not ok and "seal" in detail


def test_sealing_a_missing_artifact_refuses(tmp_path: Path, dataset: Path) -> None:
    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    with pytest.raises(FileNotFoundError) as excinfo:
        seal_artifact(tmp_path / "nothing.png", fingerprint)
    assert any("\u0600" <= ch <= "\u06ff" for ch in str(excinfo.value))


def test_the_seal_reaches_provenance_when_a_tracker_is_present(
    tmp_path: Path, figure: Path, dataset: Path
) -> None:
    tracker = ProvenanceTracker(log_dir=str(tmp_path / "prov"))
    artifacts = ArtifactManager(tracker, base_dir=str(tmp_path))
    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1", tool="dataqa")
    seal = seal_artifact(figure, fingerprint, tracker=tracker, artifacts=artifacts, kind="figure")
    assert seal.record_id
    record = tracker.get(seal.record_id)
    assert record is not None
    assert record.payload["run_hash"] == fingerprint.run_hash
    assert tracker.verify_chain()["valid"] is True
    sidecar = Path(f"{figure}.provenance.json")
    assert sidecar.exists()


def test_a_broken_tracker_degrades_the_record_not_the_seal(figure: Path, dataset: Path) -> None:
    class _Broken:
        def record(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("provenance store is down")

    fingerprint = RunFingerprint.build(code="plot()", inputs=[dataset], run_id="r1")
    seal = seal_artifact(figure, fingerprint, tracker=_Broken())
    assert seal.record_id is None
    assert verify_artifact(seal)[0] is True


# --------------------------------------------------------------------------- #
# Claim verification
# --------------------------------------------------------------------------- #


def test_a_fabricated_number_is_refused() -> None:
    report = verify_claims("Revenue grew by 42.7% this quarter.", [12.5, 3.0])
    assert report.rejected
    assert report.issues[0].text == "42.7"
    assert any("\u0600" <= ch <= "\u06ff" for ch in report.reason_fa)


def test_a_genuine_number_passes() -> None:
    assert verify_claims("Revenue grew by 23.4% this quarter.", [23.404]).grounded


def test_rounding_in_prose_is_accepted() -> None:
    assert verify_claims("The mean is 4.6.", [4.5721]).grounded
    assert verify_claims("The mean is 5.", [4.5]).grounded is False
    assert verify_claims("The total was 1200.", [1200.0]).grounded


def test_a_number_with_no_evidence_at_all_is_refused() -> None:
    report = verify_claims("The correlation is 0.87.", [])
    assert report.rejected
    assert "not backed by any computed result" in report.issues[0].reason_en


def test_evidence_can_be_waived_explicitly() -> None:
    assert verify_claims("The correlation is 0.87.", [], require_evidence=False).grounded


def test_prose_without_numbers_is_never_blocked() -> None:
    assert verify_claims("Sales rose across every region.", []).grounded


def test_grounded_values_may_be_a_mapping_or_nested() -> None:
    assert verify_claims("mean 4.5 and max 9", {"mean": 4.5, "extremes": [1, 9]}).grounded
    assert verify_claims("mean 4.5", {"stats": {"mean": 4.5}}).grounded


def test_persian_digits_are_grounded_the_same_way() -> None:
    # «رشد ۲۳٫۴ درصد بود.»
    text = (
        "\u0631\u0634\u062f \u06f2\u06f3\u066b\u06f4 \u062f\u0631\u0635\u062f "
        "\u0628\u0648\u062f."
    )
    assert verify_claims(text, [23.4]).grounded
    assert verify_claims(text, [11.1]).rejected


def test_thousands_separators_are_read_as_one_number() -> None:
    assert verify_claims("Total revenue was 1,234,567.", [1234567]).grounded
    assert extract_numbers("1,234,567")[0][1] == 1234567.0


def test_structural_numbers_are_not_treated_as_claims() -> None:
    assert verify_claims("See section 3 and figure 2.", []).grounded
    assert verify_claims("Table 4 shows the split.", []).grounded


def test_a_percentage_written_against_a_fraction_is_accepted() -> None:
    assert verify_claims("Conversion was 12%.", [0.12]).grounded


def test_one_bad_number_among_good_ones_rejects_the_claim() -> None:
    report = verify_claims("Mean 4.5, max 9, and growth 88.8%.", [4.5, 9])
    assert report.rejected
    assert [issue.text for issue in report.issues] == ["88.8"]


def test_the_report_serialises_for_a_wire_reply() -> None:
    payload = verify_claims("Growth was 42.7%.", [1.0]).to_dict()
    assert payload["grounded"] is False
    assert payload["issues"][0]["value"] == 42.7
    assert payload["reason_fa"]


def test_extract_numbers_handles_signs_and_decimals() -> None:
    values = dict(extract_numbers("from -3.5 to +7 and 0.25"))
    assert values["-3.5"] == -3.5
    assert values["+7"] == 7.0
    assert values["0.25"] == 0.25


def test_extract_numbers_on_non_text_is_empty() -> None:
    assert extract_numbers("") == []
    assert extract_numbers(None) == []  # type: ignore[arg-type]
