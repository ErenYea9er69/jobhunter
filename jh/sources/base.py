"""Base adapter contract and result structures per Section 6.4 of newall-logic.md.

Defines:
search(query, filters, cursor) -> SourcePage
get_details(source_job_id) -> SourceJob | NotSupported
check_status(source_job_ids) -> StatusBatch | NotSupported
health_check() -> SourceHealth
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from ..util import now_iso


@dataclass
class SourceJob:
    """Normalized job returned by a source adapter."""
    id: str
    title: str
    company: str
    location: str = ""
    url: str = ""
    apply_url: str = ""
    description: str = ""
    work_mode: str = ""
    salary: str = ""
    job_type: str = ""
    posted_at: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourcePage:
    """Paginated source search results."""
    source_name: str
    items: list[dict[str, Any]] = field(default_factory=list)
    cursor: Optional[str] = None
    has_more: bool = False
    total_count: Optional[int] = None
    fetched_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceHealth:
    """Health check outcome for a source adapter."""
    source_name: str
    is_available: bool = True
    latency_ms: float = 0.0
    recent_errors: list[str] = field(default_factory=list)
    rate_limit_remaining: Optional[int] = None
    last_checked_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseSourceAdapter:
    """Common interface that every job source adapter implements."""
    source_name: str = "Base"

    def search(
        self,
        query: str = "",
        filters: Optional[dict[str, Any]] = None,
        cursor: Optional[str] = None,
    ) -> SourcePage:
        """Search jobs from this source. Returns a SourcePage."""
        return SourcePage(source_name=self.source_name, items=[])

    def get_details(self, source_job_id: str) -> Optional[SourceJob]:
        """Fetch full details for one job if supported by source."""
        return None

    def check_status(self, source_job_ids: list[str]) -> dict[str, str]:
        """Check status of multiple jobs. Returns mapping {id: open|closed|stale|unknown}."""
        return {jid: "unknown" for jid in source_job_ids}

    def health_check(self) -> SourceHealth:
        """Return source health status, availability and latency."""
        return SourceHealth(source_name=self.source_name, is_available=True)
