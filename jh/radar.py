"""LinkedIn Radar worker: always-on background watcher with lifecycle deduplication and gentle adaptive polling."""
from __future__ import annotations

import datetime
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Optional

from . import db, home, pipeline

log = logging.getLogger("jobhunter.radar")

_worker_singleton: Optional[RadarWorker] = None
_worker_lock = threading.Lock()
_recent_events: list[dict[str, Any]] = []


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def acquire_radar_lock() -> bool:
    """Acquire a cross-process lock using PID file in jobmcp/run."""
    run_dir = home.get_home() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    pid_file = run_dir / "radar.pid"
    lock_file = run_dir / "radar.lock"

    if pid_file.is_file():
        try:
            existing_pid = int(pid_file.read_text().strip())
            if existing_pid == os.getpid():
                return True
            if _is_pid_alive(existing_pid):
                return False
        except Exception:
            pass

    try:
        pid_file.write_text(str(os.getpid()))
        lock_file.write_text(db.now_iso())
        return True
    except Exception as e:
        log.warning("Could not acquire radar lock: %s", e)
        return False


def release_radar_lock() -> None:
    """Release PID and lock file if owned by current process."""
    run_dir = home.get_home() / "run"
    pid_file = run_dir / "radar.pid"
    lock_file = run_dir / "radar.lock"

    try:
        if pid_file.is_file():
            existing_pid = int(pid_file.read_text().strip())
            if existing_pid == os.getpid():
                pid_file.unlink(missing_ok=True)
                lock_file.unlink(missing_ok=True)
    except Exception:
        pass


def push_radar_event(total_new: int, matching_filters: int, top_titles: list[str]) -> dict[str, Any]:
    """Push a notification event for the Web UI."""
    event = {
        "id": f"evt_{int(time.time()*1000)}",
        "total_new": total_new,
        "new_matching_filters": matching_filters,
        "top_titles": top_titles[:3],
        "created_at": db.now_iso(),
    }
    _recent_events.append(event)
    if len(_recent_events) > 50:
        _recent_events.pop(0)
    return event


def get_latest_event() -> Optional[dict[str, Any]]:
    """Return the most recent radar notification event."""
    return _recent_events[-1] if _recent_events else None


def ack_radar_jobs(job_ids: Optional[list[str]] = None) -> int:
    """Mark new jobs as acknowledged (is_new=0, seen_by_user=1)."""
    with db.session() as c:
        if job_ids:
            placeholders = ",".join("?" * len(job_ids))
            c.execute(f"""
                UPDATE jobs SET is_new=0, seen_by_user=1
                WHERE id IN ({placeholders}) OR job_key IN ({placeholders})
            """, list(job_ids) + list(job_ids))
            affected = c.execute(f"SELECT changes()").fetchone()[0]
        else:
            c.execute("UPDATE jobs SET is_new=0, seen_by_user=1 WHERE is_new=1")
            affected = c.execute("SELECT changes()").fetchone()[0]
    return affected


class RadarWorker:
    """Background LinkedIn Radar watcher."""

    def __init__(self, min_interval: int = 600, max_interval: int = 1200):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.max_backoff = 7200  # 2 hours
        self.current_interval = random.randint(self.min_interval, self.max_interval)
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        if not acquire_radar_lock():
            log.info("Radar worker already running in another process.")
            return False

        self._running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="jh-linkedin-radar")
        self.thread.start()
        log.info("LinkedIn Radar worker started on daemon thread.")
        return True

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self.stop_event.set()
        self.wake_event.set()
        db.update_radar_state(status="stopped")
        release_radar_lock()
        log.info("LinkedIn Radar worker stopped.")

    def poll_once(self) -> dict[str, Any]:
        """Run a single gentle LinkedIn incremental poll with lifecycle ingestion."""
        db.update_radar_state(status="working")
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        iso_now = now_dt.isoformat()

        try:
            # 1. Run incremental scrape
            new_discovered_count = pipeline.run_linkedin_incremental()

            # 2. Ingest staged pending jobs into jobs table
            staged = db.get_pending_jobs()
            inserted_new = []
            for j in staged:
                # Ensure source is marked LinkedIn
                if not j.get("source"):
                    j["source"] = "LinkedIn"
                res = db.ingest_job(j)
                if res and res.get("is_new"):
                    inserted_new.append(j)

            # 3. Check active view filter matches
            view_res = db.query_jobs()
            matching_new = [j for j in view_res.get("jobs", []) if j.get("is_new")]

            # 4. Trigger event if new matching jobs found
            if matching_new:
                top_titles = [j.get("title", "") for j in matching_new[:3]]
                push_radar_event(
                    total_new=len(inserted_new),
                    matching_filters=len(matching_new),
                    top_titles=top_titles,
                )

            # 5. Success reset
            self.current_interval = random.randint(self.min_interval, self.max_interval)
            next_dt = now_dt + datetime.timedelta(seconds=self.current_interval)

            db.update_radar_state(
                status="idle",
                last_poll_at=iso_now,
                next_poll_at=next_dt.isoformat(),
                interval_seconds=self.current_interval,
                failure_count=0,
                last_error="",
            )

            return {
                "success": True,
                "discovered": new_discovered_count,
                "new_ingested": len(inserted_new),
                "matching_filters": len(matching_new),
                "interval_seconds": self.current_interval,
            }

        except Exception as e:
            err_msg = str(e)
            log.warning("LinkedIn Radar poll encountered error: %s", err_msg)
            r_curr = db.get_radar_state()
            failures = r_curr.get("failure_count", 0) + 1
            # Double interval up to 2 hours
            self.current_interval = min(self.max_backoff, self.current_interval * 2)
            next_dt = now_dt + datetime.timedelta(seconds=self.current_interval)
            status = "warning" if failures >= 3 else "idle"

            db.update_radar_state(
                status=status,
                last_poll_at=iso_now,
                next_poll_at=next_dt.isoformat(),
                interval_seconds=self.current_interval,
                failure_count=failures,
                last_error=err_msg[:200],
            )

            return {
                "success": False,
                "error": err_msg,
                "failure_count": failures,
                "status": status,
                "interval_seconds": self.current_interval,
            }

    def _run_loop(self) -> None:
        # Check catch-up poll on start
        r_state = db.get_radar_state()
        last_poll = r_state.get("last_poll_at")
        should_catch_up = True

        if last_poll:
            try:
                last_dt = datetime.datetime.fromisoformat(last_poll.replace("Z", "+00:00"))
                diff_m = (datetime.datetime.now(datetime.timezone.utc) - last_dt).total_seconds() / 60.0
                if diff_m < 20.0:
                    should_catch_up = False
            except Exception:
                should_catch_up = True

        if should_catch_up:
            log.info("Radar running catch-up poll (last poll > 20 min ago or fresh start).")
            self.poll_once()

        while not self.stop_event.is_set():
            # Wait for interval or wake trigger
            woken = self.wake_event.wait(timeout=float(self.current_interval))
            self.wake_event.clear()

            if self.stop_event.is_set():
                break

            self.poll_once()


def start_radar_worker() -> bool:
    """Start global Radar worker daemon."""
    global _worker_singleton
    with _worker_lock:
        if _worker_singleton is None:
            _worker_singleton = RadarWorker()
        return _worker_singleton.start()


def stop_radar_worker() -> None:
    """Stop global Radar worker daemon."""
    global _worker_singleton
    with _worker_lock:
        if _worker_singleton is not None:
            _worker_singleton.stop()
            _worker_singleton = None


def get_radar_worker() -> Optional[RadarWorker]:
    """Get active Radar worker instance."""
    return _worker_singleton
