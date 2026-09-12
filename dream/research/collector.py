"""Multi-source evidence collection, credibility scoring, and source deduplication."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from dream.research.types import ResearchSource, SourceCredibility


class MultiSourceCollector:
    """Gathers and ranks multi-source evidence across web, documents, and local knowledge."""

    def __init__(self) -> None:
        self._academic_domains = {
            "arxiv.org",
            "nature.com",
            "ieee.org",
            "acm.org",
            "springer.com",
            "science.org",
            "biorxiv.org",
        }
        self._official_domains = {
            "github.com",
            "python.org",
            "openai.com",
            "anthropic.com",
            "nousresearch.com",
            "huggingface.co",
            "microsoft.com",
            "google.com",
            "iso.org",
            "nist.gov",
        }

    def assess_credibility(self, url: str) -> tuple[SourceCredibility, float]:
        """Classify domain credibility tier and numerical weight in [0.0, 1.0]."""
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower()

        for acad in self._academic_domains:
            if domain.endswith(acad):
                return SourceCredibility.PRIMARY_ACADEMIC, 0.98

        for off in self._official_domains:
            if domain.endswith(off):
                return SourceCredibility.OFFICIAL_DOCUMENTATION, 0.95

        if domain.endswith(".edu") or domain.endswith(".gov"):
            return SourceCredibility.PRIMARY_ACADEMIC, 0.96

        news_domains = ["reuters.com", "bloomberg.com", "bbc.com", "techcrunch.com"]
        if any(news in domain for news in news_domains):
            return SourceCredibility.NEWS_ORGANIZATION, 0.88

        comm_domains = ["reddit.com", "medium.com", "forum", "blog", "x.com"]
        if any(comm in domain for comm in comm_domains):
            return SourceCredibility.COMMUNITY_FORUM, 0.60

        return SourceCredibility.EXPERT_ANALYSIS, 0.80

    def create_source(
        self,
        url: str,
        title: str,
        snippet: str,
        extracted_claims: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchSource:
        """Instantiate a standardized ResearchSource with computed credibility score."""
        cred, score = self.assess_credibility(url)
        parsed = urlparse(url)
        domain = parsed.netloc or "local_source"
        sid = f"src_{uuid.uuid4().hex[:8]}"

        claims = extracted_claims or self._extract_key_sentences(snippet)

        return ResearchSource(
            id=sid,
            url=url,
            title=title.strip(),
            snippet=snippet.strip(),
            credibility=cred,
            credibility_score=score,
            domain=domain,
            extracted_claims=claims,
            timestamp=time.time(),
            metadata=metadata or {},
        )

    def deduplicate_sources(
        self,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        """Eliminate redundant sources matching identical URLs or near-duplicate snippets."""
        unique_urls: set[str] = set()
        deduped: list[ResearchSource] = []

        for s in sources:
            norm_url = s.url.strip().rstrip("/").lower()
            if norm_url not in unique_urls:
                unique_urls.add(norm_url)
                deduped.append(s)

        # Sort by credibility score descending
        deduped.sort(key=lambda x: x.credibility_score, reverse=True)
        return deduped

    def _extract_key_sentences(self, text: str) -> list[str]:
        """Extract substantive factual assertions from raw snippet text."""
        raw_sentences = re.split(r"[.\n!\u061f\u06d4]+", text)
        claims = [
            s.strip()
            for s in raw_sentences
            if len(s.strip().split()) >= 4
        ]
        return claims[:4]
