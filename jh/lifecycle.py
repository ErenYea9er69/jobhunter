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


def _mark_job_closed(job_id: str, reason: str) -> None:
    """Set job state to expired and initialize delete_at with cleanup_grace_hours."""
    grace_hours = int(db.get_setting("cleanup_grace_hours", "24"))
    iso_now = db.now_iso()
    delete_dt = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=grace_hours)).isoformat()

    with db.session() as c:
        row = c.execute("SELECT keep_flag, delete_at FROM jobs WHERE id=? OR job_key=?", (job_id, job_id)).fetchone()
        if row:
            if not row["keep_flag"]:
                target_delete = row["delete_at"] or delete_dt
                c.execute("""
                    UPDATE jobs SET
                        freshness_state='expired',
                        closed_checked_at=?,
                        delete_at=?
                    WHERE id=? OR job_key=?
                """, (iso_now, target_delete, job_id, job_id))
            else:
                c.execute("""
                    UPDATE jobs SET
                        freshness_state='expired',
                        closed_checked_at=?
                    WHERE id=? OR job_key=?
                """, (iso_now, job_id, job_id))


def keep_jobs(job_ids: list[str]) -> int:
    """Protect specified jobs from deletion (sets keep_flag=1, delete_at=NULL)."""
    if not job_ids:
        return 0
    with db.session() as c:
        placeholders = ",".join("?" * len(job_ids))
        c.execute(f"""
            UPDATE jobs SET
                keep_flag=1,
                delete_at=NULL
            WHERE id IN ({placeholders}) OR job_key IN ({placeholders})
        """, list(job_ids) + list(job_ids))
        return c.execute("SELECT changes()").fetchone()[0]


def mark_job_saved(job_id: str) -> None:
    """A saved job is never deleted: keep_flag is set automatically on save."""
    keep_jobs([job_id])


def mark_job_applied(job_id: str) -> None:
    """An applied job is never deleted: keep_flag is set automatically on apply."""
    keep_jobs([job_id])


def run_cleanup() -> dict[str, Any]:
    """Execute cleanup:
    1. Mark any jobs older than 60 days as expired with a delete_at warning timestamp.
    2. Permanently delete expired jobs whose delete_at timestamp has passed and keep_flag == 0.
    3. Never delete jobs saved or tracked in applications.
    4. Write tombstones for deleted jobs and log deletion count to deletions_log.
    """
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    iso_now = now_dt.isoformat()
    grace_hours = int(db.get_setting("cleanup_grace_hours", "24"))
    delete_horizon = (now_dt + datetime.timedelta(hours=grace_hours)).isoformat()

    deleted_count = 0

    with db.session() as c:
        # 1. Initialize delete_at on expired jobs that don't have it yet
        c.execute("""
            UPDATE jobs SET
                delete_at=?
            WHERE freshness_state='expired' AND delete_at IS NULL AND keep_flag=0
        """, (delete_horizon,))

        # 2. Find jobs ready for permanent deletion
        # Must have passed delete_at, keep_flag == 0, and not be present in applications
        expired_candidates = c.execute("""
            SELECT id, job_key, url_hash, fingerprint FROM jobs
            WHERE freshness_state='expired'
              AND delete_at IS NOT NULL
              AND delete_at <= ?
              AND keep_flag=0
              AND id NOT IN (SELECT job_id FROM applications WHERE job_id IS NOT NULL AND job_id != '')
              AND job_key NOT IN (SELECT job_id FROM applications WHERE job_id IS NOT NULL AND job_id != '')
        """, (iso_now,)).fetchall()

        # 3. Process deletions and write tombstones
        for row in expired_candidates:
            url_hash = row["url_hash"] or ""
            fp = row["fingerprint"] or ""
            job_id = row["id"]

            if url_hash or fp:
                db.add_tombstone(url_hash, fp, conn=c)

            c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            c.execute("DELETE FROM job_sources WHERE job_id=?", (job_id,))
            deleted_count += 1

    if deleted_count > 0:
        db.log_deletion(deleted_count)

    status = db.get_cleanup_status()
    return {
        "deleted_count": deleted_count,
        "cleanup_status": status,
        "cleaned_at": iso_now,
    }
