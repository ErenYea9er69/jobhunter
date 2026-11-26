"""In-process Hybrid background search worker manager for Claude Desktop MCP."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from . import db, home, pipeline, util

log = logging.getLogger("jobhunter.launcher")

_ACTIVE_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_SEARCH_LOCK = threading.Lock()


def get_run_dir() -> Path:
    return home.get_home() / "run"


def start_background_search(
    session_id: str,
    query: str = "",
    location: str = "",
    role_focus: Optional[list[str]] = None,
    source_filter: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Start multi-board Hybrid search in an in-process background daemon thread."""
    sid = session_id or "default"
    with _ACTIVE_SEARCH_LOCK:
        existing = _ACTIVE_SEARCH_JOBS.get(sid)
        if existing and existing.get("status") in ("running", "queued"):
            return {
                "search_job_id": existing["job_id"],
                "status": "already_running",
                "started_at": existing["started_at"],
            }

        job_id = f"search_{util.stable_id(sid, time.time())}"
        job_info = {
            "job_id": job_id,
            "session_id": sid,
            "query": query,
            "location": location,
            "role_focus": role_focus or [],
            "source_filter": source_filter or [],
            "status": "running",
            "started_at": time.time(),
            "sources_done": 0,
            "jobs_found": 0,
            "matches_count": 0,
            "first_batch_ready": False,
            "error": None,
            "sources": [],
            "events": [],
        }
        _ACTIVE_SEARCH_JOBS[sid] = job_info

    def _worker() -> None:
        start_time = time.time()

        def _prog_cb(stage: str, data: dict[str, Any]) -> None:
            with _ACTIVE_SEARCH_LOCK:
                elapsed = round(time.time() - start_time, 1)
                if stage == "init":
                    job_info["sources"] = [
                        {"name": s, "status": "running", "jobs_found": 0, "elapsed": 0.0}
                        for s in data.get("sources", [])
                    ]
                elif stage == "source_done":
                    s_name = data.get("source", "")
                    st_map = {"ok": "done", "failed": "error", "timeout": "error", "skipped": "disabled"}
                    card_st = st_map.get(data.get("state", "ok"), "done")
                    cnt = data.get("count", 0)
                    sec = round(data.get("ms", 0) / 1000.0, 1)
                    for s in job_info["sources"]:
                        if s["name"] == s_name:
                            s.update({"status": card_st, "jobs_found": cnt, "elapsed": sec})
                            break
                    else:
                        job_info["sources"].append({"name": s_name, "status": card_st, "jobs_found": cnt, "elapsed": sec})
                    job_info["sources_done"] = data.get("completed", len(job_info["sources"]))
                    job_info["jobs_found"] = data.get("raw_total", job_info["jobs_found"])

        try:
            res = pipeline.search(query=query, location=location, force_refresh=False, on_progress=_prog_cb)
            raw_jobs = res.get("jobs", []) if isinstance(res, dict) else res
            stats = db.store_jobs(raw_jobs, query=query, location=location)
            with _ACTIVE_SEARCH_LOCK:
                elapsed = round(time.time() - start_time, 1)
                job_info["status"] = "completed"
                job_info["jobs_found"] = stats.get("total", len(raw_jobs))
                job_info["sources_done"] = len(job_info.get("sources", [])) or 10
                job_info["first_batch_ready"] = True
                job_info["events"].append({
                    "type": "done",
                    "data": {"status": "completed", "total_jobs": len(raw_jobs), "done": True, "elapsed": elapsed},
                })
        except Exception as e:
            with _ACTIVE_SEARCH_LOCK:
                job_info["status"] = "failed"
                job_info["error"] = str(e)
                job_info["first_batch_ready"] = True

    threading.Thread(target=_worker, daemon=True, name=f"jh-search-{sid}").start()
    return {
        "search_job_id": job_id,
        "status": "started",
        "started_at": job_info["started_at"],
    }


def get_search_job_status(session_id: str) -> dict[str, Any]:
    sid = session_id or "default"
    with _ACTIVE_SEARCH_LOCK:
        job = _ACTIVE_SEARCH_JOBS.get(sid)
        if not job:
            return {"status": "not_started", "sources_done": 0, "jobs_found": 0, "first_batch_ready": False}
        return dict(job)


def stop_worker(session_id: str = "") -> dict[str, Any]:
    """Stop active background search tracking for a session or all sessions."""
    with _ACTIVE_SEARCH_LOCK:
        if session_id and session_id in _ACTIVE_SEARCH_JOBS:
            _ACTIVE_SEARCH_JOBS[session_id]["status"] = "stopped"
        elif not session_id:
            for s in _ACTIVE_SEARCH_JOBS.values():
                s["status"] = "stopped"
    return {
        "status": "stopped",
        "stopped_pid": None,
        "message": "JobHunter background search stopped.",
    }
