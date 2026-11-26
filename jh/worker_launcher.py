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

from . import config, db, home, pipeline, util

log = logging.getLogger("jobhunter.launcher")
ROOT = Path(__file__).resolve().parent.parent

def get_run_dir() -> Path:
    return home.get_home() / "run"

_ACTIVE_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_SEARCH_LOCK = threading.Lock()


def _is_port_open_locally(host: str, port: int, timeout: float = 0.25) -> bool:
    """Return True if something is already accepting TCP connections on host:port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(timeout)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


def find_free_port(start_port: int = 8080, max_attempts: int = 50) -> int:
    """Find the next genuinely unoccupied TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if _is_port_open_locally("127.0.0.1", port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def is_server_healthy(
    host: str = "127.0.0.1",
    port: int = 8080,
    timeout: float = 0.8,
    expected_home: Optional[str] = None,
) -> bool:
    """Check if JobHunter HTTP daemon is answering /health for the expected home directory."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobHunter-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") != "ok":
                    return False
                remote_home = data.get("home_dir")
                if remote_home and expected_home:
                    if Path(str(remote_home)).resolve() != Path(str(expected_home)).resolve():
                        return False
                return True
    except Exception:
        pass
    return False


def get_running_server_info(host: str = "127.0.0.1") -> Optional[dict[str, Any]]:
    """Check if an active server for THIS JobHunter home is recorded in jobmcp/run and answering /health."""
    run_dir = get_run_dir()
    pid_file = run_dir / "server.pid"
    port_file = run_dir / "server.port"
    expected_home = str(home.get_home().resolve())
    if pid_file.is_file() and port_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            port = int(port_file.read_text(encoding="utf-8").strip())
            if is_server_healthy(host=host, port=port, expected_home=expected_home):
                return {"pid": pid, "port": port, "healthy": True, "home_dir": expected_home}
        except Exception:
            pass
        # Stale PID/port pointing to dead or foreign server: clean lock files before launching fresh
        for f in (pid_file, port_file, run_dir / "server.lock"):
            try:
                f.unlink(missing_ok=True)
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
    run_dir = get_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
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

    # Write port, pid, and lock files early (D6)
    (run_dir / "server.port").write_text(str(port), encoding="utf-8")
    (run_dir / "server.pid").write_text(str(proc.pid), encoding="utf-8")
    (run_dir / "server.lock").write_text(str(proc.pid), encoding="utf-8")

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
    """Launch Chromium browser with ATS extension and dedicated profile."""
    if os.environ.get("JOBHUNTER_NO_BROWSER") == "1":
        log.info("Skipping browser auto-launch (JOBHUNTER_NO_BROWSER=1): %s", url)
        return False
    log.info("JobHunter Web UI available at: %s", url)
    try:
        from . import extension_installer
        res = extension_installer.launch_browser_with_extension(url)
        return bool(res.get("success", False))
    except Exception as e:
        log.warning("Could not launch browser automatically: %s", e)
        return False


def stop_worker(session_id: str = "") -> dict[str, Any]:
    """Gracefully terminate detached server worker and background jobs."""
    stopped_pid = None
    run_dir = get_run_dir()
    pid_file = run_dir / "server.pid"
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
        (run_dir / "server.pid").unlink(missing_ok=True)
        (run_dir / "server.lock").unlink(missing_ok=True)
        (run_dir / "server.port").unlink(missing_ok=True)
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
