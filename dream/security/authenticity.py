"""Artifact and claim authenticity (P6, L9-D).

The agentic surfaces produce things that look authoritative: a figure, a
table, a report sentence containing a number. Each of those is only worth
what its lineage is worth, and a language model will happily write
"revenue grew 23.4%" whether or not any code ever computed 23.4.

Two controls, both built on top of :mod:`dream.provenance` (which this
module *calls* — the tracker, its hash chain, and ``ArtifactManager`` are
not reimplemented here):

* **artifact sealing.** :func:`seal_artifact` hash-links an artifact to
  the exact code, the exact input data, and the exact run that produced
  it. The seal is a SHA-256 over those components, so re-running with a
  changed script or a changed dataset yields a different seal.
  :func:`verify_artifact` re-hashes the file on disk and reports honestly
  when it no longer matches its seal.
* **claim verification.** :func:`verify_claims` extracts every number in
  a piece of prose — English and Persian digits, percentages, thousands
  separators — and refuses any number that no computed value grounds.
  Fabrication fails; a genuine figure passes.

Fail-closed: an unreadable artifact, a missing ledger, or an unparsable
claim is *not* authentic. Refusals are bilingual.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dream.memory import normalize_fa

__all__ = [
    "ArtifactSeal",
    "ClaimIssue",
    "ClaimReport",
    "RunFingerprint",
    "extract_numbers",
    "seal_artifact",
    "verify_artifact",
    "verify_claims",
]

_CHUNK = 1024 * 1024
_MAX_HASH_BYTES = 256 * 1024 * 1024
#: Relative tolerance for matching a written number to a computed one.
#: Reports round; 23.4 must still match a computed 23.404.
DEFAULT_TOLERANCE = 0.005


def _hash_text(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8", "ignore"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def _hash_file(path: Path) -> str | None:
    """SHA-256 of a file, or ``None`` when it cannot be read or is oversize."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > _MAX_HASH_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                block = handle.read(_CHUNK)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


@dataclass(frozen=True)
class RunFingerprint:
    """What produced an artifact: the code, the inputs, and the run.

    ``run_hash`` is the identity a claim or a figure can be checked
    against. Any change to the code text, to any input file's bytes, or to
    the parameter block produces a different hash.
    """

    code_hash: str
    data_hashes: tuple[tuple[str, str], ...]
    params_hash: str
    run_id: str
    tool: str = "unknown"

    @property
    def run_hash(self) -> str:
        joined = "|".join(f"{name}:{value}" for name, value in self.data_hashes)
        return _hash_text(self.code_hash, joined, self.params_hash, self.run_id, self.tool)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code_hash": self.code_hash,
            "data_hashes": [list(pair) for pair in self.data_hashes],
            "params_hash": self.params_hash,
            "run_id": self.run_id,
            "tool": self.tool,
            "run_hash": self.run_hash,
        }

    @classmethod
    def build(
        cls,
        *,
        code: str,
        inputs: list[str | Path] | None = None,
        params: dict[str, Any] | None = None,
        run_id: str,
        tool: str = "unknown",
    ) -> RunFingerprint:
        """Fingerprint one run. Unreadable inputs are recorded as such.

        An input that cannot be hashed is not silently skipped: it is
        recorded with the sentinel ``"unreadable"`` so the seal reflects
        that the lineage is incomplete rather than pretending it is whole.
        """
        data: list[tuple[str, str]] = []
        for item in inputs or []:
            path = Path(item).expanduser()
            digest = _hash_file(path)
            data.append((path.name, digest or "unreadable"))
        data.sort()
        params_blob = (
            "" if not params else repr(sorted((str(k), str(v)) for k, v in params.items()))
        )
        return cls(
            code_hash=_hash_text(code or ""),
            data_hashes=tuple(data),
            params_hash=_hash_text(params_blob),
            run_id=str(run_id),
            tool=str(tool),
        )


@dataclass(frozen=True)
class ArtifactSeal:
    """A figure, table, or file bound to the run that produced it."""

    artifact_path: str
    artifact_hash: str
    run_hash: str
    seal: str
    record_id: str | None = None
    kind: str = "file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "run_hash": self.run_hash,
            "seal": self.seal,
            "record_id": self.record_id,
            "kind": self.kind,
        }


def seal_artifact(
    artifact_path: str | Path,
    fingerprint: RunFingerprint,
    *,
    kind: str = "file",
    tracker: Any = None,
    artifacts: Any = None,
    agent_id: str = "dream.security.authenticity",
) -> ArtifactSeal:
    """Hash-link an artifact to its run, recording provenance when available.

    *tracker* is a :class:`dream.provenance.ProvenanceTracker` and
    *artifacts* an :class:`dream.provenance.ArtifactManager`; both are
    optional so the control is testable offline, and both are used through
    their public API only. A provenance failure degrades the seal to
    ``record_id=None`` — it never silently drops the seal itself.

    Raises ``FileNotFoundError`` when the artifact cannot be hashed: an
    artifact Dream cannot read is an artifact Dream will not vouch for.
    """
    path = Path(artifact_path).expanduser()
    artifact_hash = _hash_file(path)
    if artifact_hash is None:
        raise FileNotFoundError(
            f"authenticity refused: cannot hash artifact {path}\n"
            f"اصالت رد شد: امکان هش‌گیری از خروجی {path} نیست"
        )
    run_hash = fingerprint.run_hash
    seal = _hash_text(str(path.name), artifact_hash, run_hash, str(kind))

    record_id: str | None = None
    if tracker is not None:
        try:
            record = tracker.record(
                "file_write",
                agent_id,
                payload={
                    "artifact": path.name,
                    "artifact_hash": artifact_hash,
                    "run_hash": run_hash,
                    "seal": seal,
                    "kind": kind,
                    "tool": fingerprint.tool,
                },
            )
            record_id = getattr(record, "record_id", None)
        except Exception:
            record_id = None
    if artifacts is not None and record_id:
        try:
            artifacts.link_artifact(
                str(path),
                record_id,
                tool_name=fingerprint.tool,
                agent_id=agent_id,
                custom_metadata={"run_hash": run_hash, "seal": seal, "kind": kind},
            )
        except Exception:
            pass
    return ArtifactSeal(
        artifact_path=str(path),
        artifact_hash=artifact_hash,
        run_hash=run_hash,
        seal=seal,
        record_id=record_id,
        kind=kind,
    )


def verify_artifact(seal: ArtifactSeal) -> tuple[bool, str]:
    """Re-hash the artifact and confirm the seal still holds."""
    path = Path(seal.artifact_path).expanduser()
    current = _hash_file(path)
    if current is None:
        return False, (
            "artifact unverifiable: it is missing or unreadable\n"
            "خروجی قابل راستی‌آزمایی نیست: وجود ندارد یا خوانده نمی‌شود"
        )
    if current != seal.artifact_hash:
        return False, (
            "artifact changed after it was sealed; its provenance no longer applies\n"
            "خروجی پس از مهر شدن تغییر کرده است؛ پیشینهٔ آن دیگر معتبر نیست"
        )
    expected = _hash_text(path.name, current, seal.run_hash, seal.kind)
    if expected != seal.seal:
        return False, (
            "artifact seal does not match its own components\n"
            "مهر خروجی با اجزای خودش هم‌خوان نیست"
        )
    return True, "artifact verified against its run fingerprint"


# --------------------------------------------------------------------------- #
# Claim verification
# --------------------------------------------------------------------------- #

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

#: A number written in prose: optional sign, digits with optional thousands
#: separators (ASCII comma or the Arabic thousands mark), optional decimal.
_NUMBER_RE = re.compile(
    r"[-+]?\d{1,3}(?:[,\u066c]\d{3})+(?:[.\u066b]\d+)?|[-+]?\d+(?:[.\u066b]\d+)?"
)

#: Numbers that carry no analytic claim: years, list ordinals, versions,
#: and small counts a report uses structurally ("3 sections").
_STRUCTURAL_CONTEXT = re.compile(
    r"(?:section|figure|table|step|chapter|page|version|بخش|شکل|جدول|گام|صفحه|نسخه)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClaimIssue:
    """One number in the prose that no computed value grounds."""

    value: float
    text: str
    reason_en: str
    reason_fa: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "text": self.text,
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
        }


@dataclass(frozen=True)
class ClaimReport:
    """The verdict on a piece of prose that carries numbers."""

    grounded: bool
    checked: tuple[float, ...] = field(default_factory=tuple)
    issues: tuple[ClaimIssue, ...] = field(default_factory=tuple)
    reason_en: str = ""
    reason_fa: str = ""

    @property
    def rejected(self) -> bool:
        return not self.grounded

    def to_dict(self) -> dict[str, Any]:
        return {
            "grounded": self.grounded,
            "checked": list(self.checked),
            "issues": [issue.to_dict() for issue in self.issues],
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
        }


def extract_numbers(text: str) -> list[tuple[str, float]]:
    """Every number in *text*, as ``(as-written, value)`` pairs.

    Persian and Arabic-Indic digits, Persian decimal and thousands marks,
    and ASCII thousands separators all fold to one numeric value.
    """
    if not isinstance(text, str) or not text:
        return []
    folded = normalize_fa(text).translate(_FA_DIGITS)
    found: list[tuple[str, float]] = []
    for match in _NUMBER_RE.finditer(folded):
        raw = match.group(0)
        cleaned = raw.replace(",", "").replace("\u066c", "").replace("\u066b", ".")
        try:
            value = float(cleaned)
        except ValueError:  # pragma: no cover - regex guarantees parseability
            continue
        prefix = folded[max(0, match.start() - 24): match.start()]
        if _STRUCTURAL_CONTEXT.search(prefix.rstrip()):
            continue
        found.append((raw, value))
    return found


def _matches(value: float, grounded: list[float], tolerance: float) -> bool:
    for known in grounded:
        if known == value:
            return True
        scale = max(abs(known), abs(value), 1e-9)
        if abs(known - value) <= tolerance * scale:
            return True
        # Reports commonly round: 23.4 for a computed 23.44, 1.2 for 1.23.
        for digits in (0, 1, 2, 3):
            if round(known, digits) == value:
                return True
        # Percentages written as whole numbers against a computed fraction.
        if abs(known * 100 - value) <= tolerance * max(abs(known * 100), 1e-9):
            return True
    return False


def verify_claims(
    text: str,
    grounded_values: Any,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    require_evidence: bool = True,
) -> ClaimReport:
    """Refuse prose whose numbers no computed value supports.

    *grounded_values* is whatever the run actually computed: a sequence of
    numbers, or a mapping whose values are numbers (nested lists and dicts
    are walked). Every number in *text* must match one of them, within
    *tolerance* or a sensible rounding.

    With ``require_evidence`` (the default) a numeric claim made with *no*
    evidence at all is refused rather than waved through — an assistant
    that cites a figure it never computed is the failure this control
    exists to catch.
    """
    numbers = extract_numbers(text)
    if not numbers:
        return ClaimReport(grounded=True)

    grounded = _flatten_numbers(grounded_values)
    if not grounded:
        if not require_evidence:
            return ClaimReport(grounded=True, checked=tuple(value for _, value in numbers))
        issues = tuple(
            ClaimIssue(
                value=value,
                text=raw,
                reason_en=f"the number {raw} is not backed by any computed result",
                reason_fa=f"عدد {raw} با هیچ نتیجهٔ محاسبه‌شده‌ای پشتیبانی نمی‌شود",
            )
            for raw, value in numbers
        )
        return _claim_refusal(numbers, issues)

    issues = []
    for raw, value in numbers:
        if not _matches(value, grounded, tolerance):
            issues.append(
                ClaimIssue(
                    value=value,
                    text=raw,
                    reason_en=f"the number {raw} does not match any computed result",
                    reason_fa=f"عدد {raw} با هیچ نتیجهٔ محاسبه‌شده‌ای هم‌خوان نیست",
                )
            )
    if issues:
        return _claim_refusal(numbers, tuple(issues))
    return ClaimReport(grounded=True, checked=tuple(value for _, value in numbers))


def _claim_refusal(
    numbers: list[tuple[str, float]], issues: tuple[ClaimIssue, ...]
) -> ClaimReport:
    listed = ", ".join(issue.text for issue in issues)
    return ClaimReport(
        grounded=False,
        checked=tuple(value for _, value in numbers),
        issues=issues,
        reason_en=(
            f"claim refused: {listed} is not grounded in a computed result. "
            "Dream does not publish numbers it cannot trace to code and data."
        ),
        reason_fa=(
            f"ادعا رد شد: {listed} بر نتیجهٔ محاسبه‌شده استوار نیست. "
            "دریم عددی را که به کد و داده ردیابی نشود منتشر نمی‌کند."
        ),
    )


def _flatten_numbers(value: Any) -> list[float]:
    out: list[float] = []
    stack = [value]
    seen = 0
    while stack and seen < 10_000:
        item = stack.pop()
        seen += 1
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            out.append(float(item))
        elif isinstance(item, str):
            try:
                out.append(float(item.replace(",", "")))
            except ValueError:
                out.extend(number for _, number in extract_numbers(item))
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set)):
            stack.extend(item)
    return out
