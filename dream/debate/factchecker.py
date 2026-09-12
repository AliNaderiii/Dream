"""Automated claim extraction, logical fallacy detection, and evidence verification."""

from __future__ import annotations

import re
import time
import uuid

from dream.debate.types import FactClaim, VerificationStatus


class FactChecker:
    """Extracts statements, checks for logical fallacies, and verifies grounded truth."""

    FALLACY_PATTERNS = [
        (
            r"(یا\s+باید\s+.*\s+یا\s+نابودی|either\s+.*\s+or\s+total\s+ruin)",
            "مغالطه دوراهی کاذب (False Dilemma)",
        ),
        (
            r"(همه\s+می\u200cدانند|everyone\s+knows|بدون\s+شک\s+همه)",
            "مغالطه تعمیم شتاب‌زده (Hasty Generalization)",
        ),
        (
            r"(تو\s+نمی\u200cفهمی|شما\s+صلاحیت\s+ندارید|you\s+are\s+ignorant)",
            "مغالطه حمله به شخص (Ad Hominem)",
        ),
        (
            r"(چون\s+من\s+می\u200cگویم\s+پس\s+درست\s+است|because\s+i\s+said\s+so)",
            "مغالطه استدلال دایره‌ای (Circular Reasoning)",
        ),
    ]

    def detect_fallacies(self, text: str) -> list[str]:
        """Detect known rhetorical fallacies in argumentation text."""
        detected: list[str] = []
        for pat, name in self.FALLACY_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                detected.append(name)
        return detected

    def extract_claims(self, text: str) -> list[FactClaim]:
        """Decompose an argument into atomic factual statements."""
        raw_sentences = [
            s.strip()
            for s in re.split(r"[\.\n!\?\u061f\u06d4]+", text)
            if len(s.strip()) > 8
        ]

        claims: list[FactClaim] = []
        for sent in raw_sentences:
            cid = f"clm-{uuid.uuid4().hex[:6]}"
            fallacies = self.detect_fallacies(sent)
            claims.append(
                FactClaim(
                    claim_id=cid,
                    statement=sent,
                    verification_status=VerificationStatus.UNVERIFIED,
                    confidence_score=0.5,
                    fallacies_detected=fallacies,
                )
            )
        return claims

    def verify_claim_against_evidence(
        self,
        claim: FactClaim,
        evidence: str = "",
    ) -> FactClaim:
        """Verify claim against provided ground-truth evidence text."""
        if not evidence.strip():
            claim.verification_status = VerificationStatus.UNVERIFIED
            claim.confidence_score = 0.5
            return claim

        claim_words = set(re.findall(r"\w+", claim.statement.lower()))
        evidence_words = set(re.findall(r"\w+", evidence.lower()))

        if not claim_words:
            claim.verification_status = VerificationStatus.UNVERIFIED
            return claim

        overlap = len(claim_words.intersection(evidence_words))
        ratio = overlap / len(claim_words)

        # Check contradiction negation keywords
        contradiction_markers = [
            "غلط",
            "نادرست",
            "رد شده",
            "false",
            "incorrect",
            "refuted",
            "disproven",
        ]
        has_contradiction = (
            any(m in evidence.lower() for m in contradiction_markers) and ratio > 0.3
        )

        if has_contradiction:
            claim.verification_status = VerificationStatus.CONTRADICTED
            claim.confidence_score = round(max(0.1, 1.0 - ratio), 2)
            claim.evidence_sources.append(evidence[:120])
        elif ratio >= 0.4:
            claim.verification_status = VerificationStatus.VERIFIED
            claim.confidence_score = round(min(0.95, 0.5 + (ratio * 0.5)), 2)
            claim.evidence_sources.append(evidence[:120])
        elif ratio >= 0.2:
            claim.verification_status = VerificationStatus.PARTIAL
            claim.confidence_score = round(ratio, 2)
            claim.evidence_sources.append(evidence[:120])
        else:
            claim.verification_status = VerificationStatus.UNVERIFIED
            claim.confidence_score = 0.4

        claim.verified_at = time.time()
        return claim
