"""Job Freshness lifecycle per Section 9.2 of newall-logic.md.

Tracks and computes job freshness states:
- open: A source confirmed the role as active.
- closed: A source explicitly confirmed that the role closed.
- stale: The last confirmation is older than the configured freshness window.
- unknown: The source does not provide a reliable status check or dates are missing.
"""

from __future__ import annotations

import datetime
import enum
from typing import Any, Optional

from .util import days_since, parse_date


class FreshnessState(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    STALE = "stale"
    UNKNOWN = "unknown"


def calculate_posted_hours(job: dict[str, Any]) -> Optional[int]:
    """Calculate how many hours ago the job was posted.
    Prefers the company's own career page timestamp when available over aggregators (R9).
    """
    # 1. Prefer direct company career page timestamp if present
    posted_raw = (
        job.get("career_page_posted_at")
        or job.get("company_posted_at")
        or job.get("direct_posted_at")
    )

    # 2. If primary source is a direct company career board / ATS, prioritize its timestamp
    if not posted_raw:
        direct_sources = {"greenhouse", "lever", "ashby", "workday", "smartrecruiters", "career_page", "company"}
        src = str(job.get("source") or "").lower()
        sources = [str(s).lower() for s in (job.get("sources") or [])]
        if any(ds in src for ds in direct_sources) or any(any(ds in s for ds in direct_sources) for s in sources):
            posted_raw = job.get("posted_at") or job.get("published_at") or job.get("created_at")

    # 3. Fallback to standard posting timestamps
    if not posted_raw:
        posted_raw = (
            job.get("posted_at")
            or job.get("published_at")
            or job.get("created_at")
            or job.get("discovered_at")
            or job.get("found_at")
            or job.get("ingested_at")
            or job.get("last_verified_at")
        )

    if not posted_raw:
        return None

    dt = parse_date(posted_raw)
    if not dt:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    diff_seconds = (now - dt).total_seconds()
    if diff_seconds < 0:
        return 0
    return int(diff_seconds // 3600)


def is_fresh_48h(job: dict[str, Any]) -> bool:
    """Check if a job is fresh (posted within the last 48 hours) (R9)."""
    hours = calculate_posted_hours(job)
    if hours is not None:
        return hours <= 48
    d = days_since(job.get("posted_at") or job.get("published_at"))
    if d is not None:
        return d <= 2
    if job.get("is_new") or job.get("discovered_at") or job.get("found_at") or job.get("ingested_at"):
        return True
    return False


def format_freshness_badge(job: dict[str, Any]) -> dict[str, Any]:
    """Generate UI freshness badge and age label (R9).
    Returns dictionary with 'badge', 'label', 'posted_hours_ago', and 'is_fresh'.
    """
    hours = calculate_posted_hours(job)
    if hours is not None:
        is_fresh = hours <= 48
        if hours == 0:
            label = "posted just now"
        elif hours == 1:
            label = "posted 1 hour ago"
        else:
            label = f"posted {hours} hours ago"
        badge = "fresh, under 48 hours" if is_fresh else None
        return {
            "badge": badge,
            "label": label,
            "posted_hours_ago": hours,
            "is_fresh": is_fresh,
        }

    if job.get("is_new"):
        return {
            "badge": "fresh, under 48 hours",
            "label": "posted just now",
            "posted_hours_ago": 0,
            "is_fresh": True,
        }

    return {
        "badge": None,
        "label": "posted date unknown",
        "posted_hours_ago": None,
        "is_fresh": False,
    }


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


