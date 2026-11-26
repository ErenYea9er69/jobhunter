"""Job Lifecycle Management: deduplication, reposts, freshness tracking, liveness checks, and 24h grace cleanup."""
from __future__ import annotations

import datetime
import http.client
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import db, dedup

log = logging.getLogger("jobhunter.lifecycle")

_liveness_cache: dict[str, tuple[float, bool, int, str]] = {}
LIVENESS_CACHE_TTL = 3600  # 1 hour

EXPIRED_PHRASES = [
    "no longer accepting applications",
    "job is no longer available",
    "this job has expired",
    "position has been filled",
    "posting has closed",
    "this posting has expired",
    "job opening has been closed",
    "job has been removed",
]


def liveness_check(url: str, job_id: Optional[str] = None) -> dict[str, Any]:
    """Check whether a job posting URL is still live. Follows redirects and caches results for 1 hour.
    Marks 404, 410, or 'no longer accepting applications' as expired with 24h grace deletion.
    """
    if not url:
        return {"is_live": True, "status_code": 200, "reason": "No URL to verify"}

    now_t = time.time()
    # Check 1-hour cache
    if url in _liveness_cache:
        cached_t, is_live, code, reason = _liveness_cache[url]
        if now_t - cached_t < LIVENESS_CACHE_TTL:
            if not is_live and job_id:
                _mark_job_closed(job_id, reason)
            return {"is_live": is_live, "status_code": code, "reason": reason, "cached": True}

    is_live = True
    status_code = 200
    reason = "Active"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            status_code = resp.status
            if status_code in (404, 410):
                is_live = False
                reason = f"HTTP {status_code}"
            else:
                body_sample = resp.read(4096).decode("utf-8", errors="ignore").lower()
                for phrase in EXPIRED_PHRASES:
                    if phrase in body_sample:
                        is_live = False
                        reason = f"Posting expired: '{phrase}'"
                        break
    except urllib.error.HTTPError as e:
        status_code = e.code
        if status_code in (404, 410):
            is_live = False
            reason = f"HTTP {status_code}"
        else:
            is_live = True
            reason = f"HTTP {status_code} (assumed live)"
    except Exception as e:
        # Network timeout or block: assumed live, not marked dead on ambiguous network error
        status_code = 0
        is_live = True
        reason = f"Verification skipped: {e}"

    _liveness_cache[url] = (now_t, is_live, status_code, reason)

    if not is_live and job_id:
        _mark_job_closed(job_id, reason)

    return {"is_live": is_live, "status_code": status_code, "reason": reason, "cached": False}


def ingest_job(job: dict[str, Any], conn: Any = None) -> dict[str, Any]:
    """Ingest job with deduplication and lifecycle management."""
    return db.ingest_job(job, conn=conn)


def mark_expired(job_id: str, reason: str = "Expired") -> None:
    """Mark a job posting as expired with 24h grace deletion."""
    _mark_job_closed(job_id, reason)


def is_deleted(job_id: str) -> bool:
    """True if job no longer exists in jobs store."""
    return not db.job_exists(job_id)


def _mark_job_closed(job_id: str, reason: str) -> None:
    """Set job state to expired and initialize delete_at with cleanup_grace_hours."""
    grace_hours = int(db.get_setting("cleanup_grace_hours", "24"))
    delete_dt = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=grace_hours)).isoformat()
    db.mark_job_closed_record(job_id, delete_dt)


def keep_jobs(job_ids: list[str]) -> int:
    """Protect specified jobs from deletion (sets keep_flag=1, delete_at=NULL)."""
    return db.keep_jobs_by_ids(job_ids)


def mark_job_saved(job_id: str) -> None:
    """A saved job is never deleted: keep_flag is set automatically on save."""
    keep_jobs([job_id])


def mark_job_applied(job_id: str) -> None:
    """An applied job is never deleted: keep_flag is set automatically on apply."""
    keep_jobs([job_id])


def evaluate_job_flags(job: dict[str, Any], career_board_jobs: list[dict] | None = None) -> dict[str, Any]:
    """Calculate ghost score, scam warning, unverified flag, and salary flags for a job posting."""
    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    desc = (job.get("description") or "").lower()
    days_old = float(job.get("days_old") or 0)
    if not days_old and job.get("date_posted"):
        try:
            posted_dt = datetime.datetime.fromisoformat(str(job["date_posted"]).replace("Z", "+00:00"))
            days_old = max(0.0, (datetime.datetime.now(datetime.timezone.utc) - posted_dt).total_seconds() / 86400.0)
        except Exception:
            days_old = 0.0

    repost_count = int(job.get("repost_count") or 0)
    salary_min = float(job.get("salary_min") or 0)
    salary_max = float(job.get("salary_max") or 0)
    no_salary = (salary_min <= 0 and salary_max <= 0 and not job.get("salary_range"))

    # 1. Scam Warning: asks for money or move to private chat app
    scam_keywords = ["telegram", "whatsapp", "wire transfer", "cashier's check", "gift card", "crypto", "western union"]
    money_keywords = ["pay fee", "registration fee", "equipment fee", "training fee", "application fee", "pay a fee", "pay $", "send money"]
    
    is_scam = False
    scam_reasons = []
    if any(k in desc for k in money_keywords):
        is_scam = True
        scam_reasons.append("Posting asks for money or upfront fee")
    if any(k in desc for k in scam_keywords):
        is_scam = True
        scam_reasons.append("Posting directs applicant to private chat app or suspicious payment method")

    # 2. Ghost Score (0 - 100): Age (> 30 days), repost count (>= 2), missing salary
    ghost_score = 0
    ghost_reasons = []
    if days_old >= 60:
        ghost_score += 45
        ghost_reasons.append(f"Posting age is {int(days_old)} days")
    elif days_old >= 30:
        ghost_score += 30
        ghost_reasons.append(f"Posting age is {int(days_old)} days")

    if repost_count >= 3:
        ghost_score += 35
        ghost_reasons.append(f"Reposted {repost_count} times")
    elif repost_count >= 1:
        ghost_score += 20
        ghost_reasons.append(f"Reposted {repost_count} times")

    if no_salary:
        ghost_score += 20
        ghost_reasons.append("No salary disclosed")

    ghost_score = min(100, ghost_score)
    ghost_reason_str = "; ".join(ghost_reasons) if ghost_reasons else "Active fresh posting"

    # 3. Unverified Flag: Classic job missing from company's own direct ATS / career board
    unverified = False
    if career_board_jobs is not None:
        matching = [
            cb for cb in career_board_jobs
            if cb.get("company", "").lower() == company.lower()
            and (title.lower() in cb.get("title", "").lower() or cb.get("title", "").lower() in title.lower())
        ]
        unverified = len(matching) == 0
    else:
        unverified = not bool(job.get("is_direct_ats"))

    return {
        "scam_warning": is_scam,
        "scam_reason": "; ".join(scam_reasons),
        "ghost_score": ghost_score,
        "ghost_reason": ghost_reason_str,
        "unverified": unverified,
        "no_salary": no_salary,
    }


def run_cleanup() -> dict[str, Any]:
    """Execute cleanup:
    1. Mark any jobs older than 60 days as expired with a delete_at warning timestamp.
    2. Permanently delete expired jobs whose delete_at timestamp has passed and keep_flag == 0.
    3. Never delete jobs saved or tracked in applications.
    4. Write tombstones for deleted jobs and log deletion count to deletions_log.
    """
    iso_now = db.now_iso()
    grace_hours = int(db.get_setting("cleanup_grace_hours", "24"))
    deleted_count = db.cleanup_expired_records(grace_hours)

    if deleted_count > 0:
        db.log_deletion(deleted_count)

    status = db.get_cleanup_status()
    return {
        "deleted_count": deleted_count,
        "cleanup_status": status,
        "cleaned_at": iso_now,
    }
