"""Refresh scheduler for non-LinkedIn sources with adaptive TTL and 15-minute cooldown."""
from __future__ import annotations

import concurrent.futures as cf
import datetime
import logging
from typing import Any, Callable, Optional

from . import db

log = logging.getLogger("jobhunter.refresh")

NON_RADAR_SOURCES = [
    "Indeed",
    "Built In",
    "Jobicy",
    "RemoteOK",
    "Working Nomads",
    "Greenhouse",
    "Lever",
    "Ashby",
    "SmartRecruiters",
    "Workable"
]

BASE_TTL = 43200   # 12 hours
MIN_TTL = 21600    # 6 hours
MAX_TTL = 172800   # 48 hours
COOLDOWN_SECONDS = 900  # 15 minutes


def compute_new_ttl(current_ttl: int, new_ratio: float) -> int:
    """Adaptive TTL adjustment based on yield:
    - > 20% new jobs: cut TTL in half (x0.5), floor 6 hours.
    - < 5% new jobs: increase TTL by 1.5 (x1.5), ceiling 48 hours.
    - 5% to 20% new: leave TTL unchanged.
    """
    ttl = current_ttl or BASE_TTL
    if new_ratio > 0.20:
        return max(MIN_TTL, int(ttl * 0.5))
    elif new_ratio < 0.05:
        return min(MAX_TTL, int(ttl * 1.5))
    return ttl


def get_all_refresh_status() -> dict[str, Any]:
    """Retrieve refresh state, next due time, and health for all non-Radar sources."""
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    states = []
    min_remaining_seconds = None

    for s in NON_RADAR_SOURCES:
        st = db.get_refresh_state(s)
        last_run = st.get("last_run_at")
        ttl = st.get("ttl_seconds") or BASE_TTL

        next_due_dt = None
        is_due = False
        remaining_seconds = 0
        in_cooldown = False

        if last_run:
            try:
                last_dt = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                elapsed = (now_dt - last_dt).total_seconds()
                in_cooldown = elapsed < COOLDOWN_SECONDS
                next_due_dt = last_dt + datetime.timedelta(seconds=ttl)
                remaining = (next_due_dt - now_dt).total_seconds()
                if remaining <= 0:
                    is_due = not in_cooldown
                    remaining_seconds = 0
                else:
                    remaining_seconds = int(remaining)
            except Exception:
                is_due = True
        else:
            is_due = True
            remaining_seconds = 0

        if remaining_seconds > 0:
            if min_remaining_seconds is None or remaining_seconds < min_remaining_seconds:
                min_remaining_seconds = remaining_seconds

        states.append({
            "source": s,
            "last_run_at": last_run,
            "next_due_at": next_due_dt.isoformat() if next_due_dt else None,
            "ttl_seconds": ttl,
            "remaining_seconds": remaining_seconds,
            "is_due": is_due,
            "in_cooldown": in_cooldown,
            "last_total": st.get("last_total", 0),
            "last_new": st.get("last_new", 0),
            "last_new_ratio": st.get("last_new_ratio", 0.0),
        })

    return {
        "sources": states,
        "min_remaining_seconds": min_remaining_seconds or 0,
        "checked_at": now_dt.isoformat(),
    }


def run_refresh(source: Optional[str] = None, force: bool = False, scraper_fn: Optional[Callable] = None) -> dict[str, Any]:
    """Execute refresh on due sources or forced sources respecting 15-minute cooldown.
    Supports partial failure resilience: keeps results from sources that worked without failing the batch.
    """
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    iso_now = now_dt.isoformat()

    target_sources = [source] if (source and source in NON_RADAR_SOURCES) else NON_RADAR_SOURCES
    due_sources = []
    skipped_sources = []

    for s in target_sources:
        st = db.get_refresh_state(s)
        last_run = st.get("last_run_at")
        ttl = st.get("ttl_seconds") or BASE_TTL

        if last_run:
            try:
                last_dt = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                elapsed = (now_dt - last_dt).total_seconds()
                if elapsed < COOLDOWN_SECONDS:
                    skipped_sources.append({"source": s, "reason": "cooldown", "cooldown_remaining_seconds": int(COOLDOWN_SECONDS - elapsed)})
                    continue
                if force or elapsed >= ttl:
                    due_sources.append(s)
                else:
                    skipped_sources.append({"source": s, "reason": "not_due", "due_in_seconds": int(ttl - elapsed)})
            except Exception:
                due_sources.append(s)
        else:
            due_sources.append(s)

    # If no sources are due, inform caller
    if not due_sources:
        status_info = get_all_refresh_status()
        min_secs = status_info.get("min_remaining_seconds") or 0
        min_mins = max(1, int(min_secs / 60))
        return {
            "status": "fresh",
            "message": f"Sources are fresh. Next refresh due in {min_mins} minutes.",
            "min_remaining_seconds": min_secs,
            "ran": [],
            "skipped": skipped_sources,
        }

    ran_results = []

    def _fetch_source(src_name: str):
        if scraper_fn:
            return scraper_fn(src_name)
        # Default fallback if no custom scraper_fn passed
        from . import sources
        s_obj = next((s for s in sources.SEARCH_SOURCES if s.name.lower() == src_name.lower()), None)
        if s_obj and s_obj.available():
            vf = db.get_view_filters()
            q = vf.get("job_style") or "tech"
            return s_obj.fetch(q, "")
        return []

    with cf.ThreadPoolExecutor(max_workers=min(4, len(due_sources))) as pool:
        futures = {pool.submit(_fetch_source, s): s for s in due_sources}
        for fut in cf.as_completed(futures):
            src_name = futures[fut]
            curr_state = db.get_refresh_state(src_name)
            curr_ttl = curr_state.get("ttl_seconds") or BASE_TTL
            try:
                raw_jobs = fut.result()
                jobs_list = raw_jobs if isinstance(raw_jobs, list) else (raw_jobs.get("jobs", []) if isinstance(raw_jobs, dict) else [])
                # Lifecycle ingestion
                store_res = db.store_jobs(jobs_list, query=src_name)
                total_count = store_res.get("total", 0)
                new_count = store_res.get("inserted", 0)
                new_ratio = (new_count / total_count) if total_count > 0 else 0.0

                new_ttl = compute_new_ttl(curr_ttl, new_ratio)
                db.update_refresh_state(
                    src_name,
                    last_run_at=iso_now,
                    ttl_seconds=new_ttl,
                    last_new_ratio=round(new_ratio, 3),
                    last_total=total_count,
                    last_new=new_count,
                )
                ran_results.append({
                    "source": src_name,
                    "status": "success",
                    "total": total_count,
                    "new": new_count,
                    "new_ratio": round(new_ratio, 3),
                    "previous_ttl": curr_ttl,
                    "new_ttl": new_ttl,
                })
            except Exception as e:
                log.warning("Refresh failed for source '%s': %s", src_name, e)
                # Keep TTL unchanged on failure, record error, do not fail batch
                db.update_refresh_state(
                    src_name,
                    last_run_at=iso_now,
                    ttl_seconds=curr_ttl,
                )
                ran_results.append({
                    "source": src_name,
                    "status": "error",
                    "error": str(e)[:160],
                    "ttl_seconds": curr_ttl,
                })

    return {
        "status": "ok",
        "message": f"Refreshed {len(ran_results)} source(s).",
        "ran": ran_results,
        "skipped": skipped_sources,
        "refreshed_at": iso_now,
    }
