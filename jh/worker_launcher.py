"""Detached Worker Launcher & Background Search Manager (V3).

Launches server.py as a detached OS process independent of the agent or MCP process.
Starts background search jobs with lifecycle tracking.
Opens user browser or falls back cleanly in headless environments.
Ensures zero-block immediate return (< 3s).
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Optional

from . import config, db, pipeline, util

log = logging.getLogger("jobhunter.launcher")
ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "jobmcp" / "run"

_ACTIVE_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_SEARCH_LOCK = threading.Lock()


def find_free_port(start_port: int = 8080, max_attempts: int = 50) -> int:
    """Find the next available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def is_server_healthy(host: str = "127.0.0.1", port: int = 8080, timeout: float = 0.8) -> bool:
    """Check if JobHunter HTTP daemon is answering /health."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobHunter-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok"
    except Exception:
        pass
    return False


def get_running_server_info(host: str = "127.0.0.1") -> Optional[dict[str, Any]]:
    """Check if an active server is recorded in jobmcp/run and answering /health."""
    pid_file = RUN_DIR / "server.pid"
    port_file = RUN_DIR / "server.port"
    if pid_file.is_file() and port_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            port = int(port_file.read_text(encoding="utf-8").strip())
            if is_server_healthy(host=host, port=port):
                return {"pid": pid, "port": port, "healthy": True}
        except Exception:
            pass
    return None


def poll_health_in_background(host: str, port: int, max_seconds: int = 15) -> None:
    """Background thread polling /health up to max_seconds without blocking caller."""
    def _poll():
        start = time.time()
        while time.time() - start < max_seconds:
            if is_server_healthy(host=host, port=port, timeout=0.5):
                log.info(f"Detached server on {host}:{port} is healthy.")
                return
            time.sleep(0.4)
        log.warning(f"Server on {host}:{port} did not report healthy within {max_seconds}s.")

    t = threading.Thread(target=_poll, daemon=True, name="jh-health-poller")
    t.start()


def start_detached_server(host: str = "127.0.0.1", preferred_port: int = 8080, ws_dir: str = "") -> dict[str, Any]:
    """Start server.py as a detached process or reuse existing healthy instance.
    
    Returns in < 500ms.
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    existing = get_running_server_info(host=host)
    if existing:
        return {
            "status": "reused",
            "host": host,
            "port": existing["port"],
            "pid": existing["pid"],
            "url": f"http://{host}:{existing['port']}",
        }

    port = find_free_port(start_port=preferred_port)
    server_py = ROOT / "server.py"
    ws = ws_dir or config.WORKSPACE_DIR or str(ROOT)

    cmd = [sys.executable, str(server_py), "--host", host, "--port", str(port), "--ws-dir", ws]

    # Process independence: DETACHED_PROCESS and CREATE_NEW_PROCESS_GROUP on Windows, start_new_session on POSIX
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }

    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS |
            subprocess.CREATE_NEW_PROCESS_GROUP
        )
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    # Write port file early
    (RUN_DIR / "server.port").write_text(str(port), encoding="utf-8")
    (RUN_DIR / "server.pid").write_text(str(proc.pid), encoding="utf-8")

    # Start health poller in background thread (never block caller)
    poll_health_in_background(host, port, max_seconds=15)

    return {
        "status": "started",
        "host": host,
        "port": port,
        "pid": proc.pid,
        "url": f"http://{host}:{port}",
    }


def start_background_search(session_id: str, query: str = "", location: str = "",
                            role_focus: Optional[list[str]] = None,
                            source_filter: Optional[list[str]] = None) -> dict[str, Any]:
    """Start search as an asynchronous worker job or reuse running search."""
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

    def _worker():
        start_time = time.time()

        def _prog_cb(stage: str, data: dict[str, Any]) -> None:
            with _ACTIVE_SEARCH_LOCK:
                now = time.time()
                elapsed = round(now - start_time, 1)
                if stage == "init":
                    src_labels = data.get("sources", [])
                    job_info["sources"] = [
                        {"name": s, "status": "running", "jobs_found": 0, "elapsed": 0.0}
                        for s in src_labels
                    ]
                    job_info["events"].append({
                        "type": "progress",
                        "data": {"sources": list(job_info["sources"]), "done": False, "elapsed": elapsed}
                    })
                elif stage == "source_done":
                    s_name = data.get("source", "")
                    st = data.get("state", "ok")
                    cnt = data.get("count", 0)
                    sec = round(data.get("ms", 0) / 1000.0, 1)
                    st_map = {"ok": "done", "failed": "error", "timeout": "error", "skipped": "disabled"}
                    card_st = st_map.get(st, "done")
                    for s in job_info["sources"]:
                        if s["name"] == s_name:
                            s["status"] = card_st
                            s["jobs_found"] = cnt
                            s["elapsed"] = sec
                            break
                    else:
                        job_info["sources"].append({
                            "name": s_name, "status": card_st, "jobs_found": cnt, "elapsed": sec
                        })
                    job_info["sources_done"] = data.get("completed", len(job_info["sources"]))
                    job_info["jobs_found"] = data.get("raw_total", job_info["jobs_found"])
                    job_info["events"].append({
                        "type": "progress",
                        "data": {"sources": list(job_info["sources"]), "done": False, "elapsed": elapsed}
                    })

        try:
            res = pipeline.search(
                query=query,
                location=location,
                force_refresh=False,
                on_progress=_prog_cb,
            )
            raw_jobs = res.get("jobs", []) if isinstance(res, dict) else res
            
            stats = db.store_jobs(raw_jobs, query=query, location=location)
            
            with _ACTIVE_SEARCH_LOCK:
                elapsed = round(time.time() - start_time, 1)
                job_info["status"] = "completed"
                job_info["jobs_found"] = stats.get("total", len(raw_jobs))
                job_info["sources_done"] = len(job_info.get("sources", [])) or 10
                job_info["first_batch_ready"] = True
                for j in raw_jobs:
                    job_info["events"].append({"type": "job", "data": {"job": j}})
                job_info["events"].append({
                    "type": "done",
                    "data": {
                        "status": "completed",
                        "sources": list(job_info["sources"]),
                        "total_jobs": len(raw_jobs),
                        "done": True,
                        "elapsed": elapsed
                    }
                })
                
        except Exception as e:
            with _ACTIVE_SEARCH_LOCK:
                job_info["status"] = "failed"
                job_info["error"] = str(e)
                job_info["first_batch_ready"] = True
                job_info["events"].append({
                    "type": "done",
                    "data": {"status": "failed", "error": str(e), "done": True}
                })

    t = threading.Thread(target=_worker, daemon=True, name=f"jh-search-{sid}")
    t.start()

    return {
        "search_job_id": job_id,
        "status": "started",
        "started_at": job_info["started_at"],
    }


def get_search_job_status(session_id: str) -> dict[str, Any]:
    """Retrieve live search job statistics."""
    sid = session_id or "default"
    with _ACTIVE_SEARCH_LOCK:
        job = _ACTIVE_SEARCH_JOBS.get(sid)
        if not job:
            return {
                "status": "not_started",
                "sources_done": 0,
                "jobs_found": 0,
                "first_batch_ready": False,
            }
        return dict(job)


def open_browser(url: str) -> bool:
    """Launch user browser with autofill extension without throwing errors on displayless setups."""
    try:
        from . import extension_installer
        ext_res = extension_installer.launch_browser_with_extension(url=url)
        if ext_res.get("success"):
            return True
    except Exception:
        pass
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def stop_worker(session_id: str = "") -> dict[str, Any]:
    """Gracefully terminate detached server worker and background jobs."""
    stopped_pid = None
    pid_file = RUN_DIR / "server.pid"
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            stopped_pid = pid
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 15)
        except Exception:
            pass

    try:
        (RUN_DIR / "server.pid").unlink(missing_ok=True)
        (RUN_DIR / "server.lock").unlink(missing_ok=True)
        (RUN_DIR / "server.port").unlink(missing_ok=True)
    except Exception:
        pass

    with _ACTIVE_SEARCH_LOCK:
        if session_id and session_id in _ACTIVE_SEARCH_JOBS:
            _ACTIVE_SEARCH_JOBS[session_id]["status"] = "stopped"
        elif not session_id:
            for s in _ACTIVE_SEARCH_JOBS.values():
                s["status"] = "stopped"

    return {
        "status": "stopped",
        "stopped_pid": stopped_pid,
        "message": f"JobHunter worker (PID: {stopped_pid}) and search jobs stopped.",
    }
