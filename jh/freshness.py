"""Job Freshness lifecycle per Section 9.2 of newall-logic.md.

Tracks and computes job freshness states:
- open: A source confirmed the role as active.
- closed: A source explicitly confirmed that the role closed.
- stale: The last confirmation is older than the configured freshness window.
- unknown: The source does not provide a reliable status check or dates are missing.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, Optional

from .util import days_since, parse_date


class FreshnessState(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    STALE = "stale"
    UNKNOWN = "unknown"


def evaluate_freshness(job: dict[str, Any], max_age_days: int = 30) -> FreshnessState:
    """Evaluate whether a job posting is open, closed, stale, or unknown."""
    if bool(job.get("is_closed")):
        return FreshnessState.CLOSED

    # If explicit verified active timestamp exists
    verified_at = job.get("last_verified_at") or job.get("verified_at")
    if verified_at:
        d = days_since(verified_at)
        if d is not None:
            if d <= max_age_days:
                return FreshnessState.OPEN
            return FreshnessState.STALE

    # Check posted_at timestamp
    posted_at = job.get("posted_at") or job.get("published_at")
    if posted_at:
        d = days_since(posted_at)
        if d is not None:
            if d <= max_age_days:
                return FreshnessState.OPEN
            return FreshnessState.STALE

    return FreshnessState.UNKNOWN


def is_stale(job: dict[str, Any], freshness_window_days: int = 30) -> bool:
    """Return True if job is stale according to freshness window."""
    return evaluate_freshness(job, max_age_days=freshness_window_days) == FreshnessState.STALE
