"""Tests for D6: Detached worker launch (<3s), pid/lock file in jobmcp/run,
and stripping job records (no title, company, link, score) from all MCP replies.
"""
import pytest
from jh import config, db, ticket_manager, home
from jh.v5_tools import jh_status, jh_search, jh_launch, jh_query


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d6_jh_status_stripped_of_job_data():
    sid = "test_d6_status"
    # Insert a dummy job into database
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, url, fit_score, freshness_state, job_json, created_at, updated_at)
            VALUES ('job_d6_1', 'key_d6_1', 'Senior Secret Engineer', 'SecretCorp', 'Tunis', 'https://apply.secret', 95, 'active', '{}', '2026-11-24', '2026-11-24')
        """)

    sess = ticket_manager.get_or_create_session(sid)
    sess["session_state"] = ticket_manager.SessionState.LAUNCHED

    res = jh_status(session_id=sid, include_matches=True)
    assert res["status"] == "ok"
    
    # Check that no job details are returned in data
    res_str = str(res)
    assert "Senior Secret Engineer" not in res_str
    assert "SecretCorp" not in res_str
    assert "https://apply.secret" not in res_str
    assert "top_5_matches" not in res["data"]
    assert "top_matches" not in res
    assert "matches" in res["data"]
    assert "total_jobs" in res["data"]
    assert "ui_url" in res["data"]


def test_d6_jh_search_stripped_of_job_preview(monkeypatch):
    from jh import pipeline
    monkeypatch.setattr(pipeline, "search", lambda *a, **kw: {"jobs": [], "total_stored": 0, "sources": []})

    sid = "test_d6_search"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.ANSWERED)
    tkt = ticket_manager.generate_ticket(sid, "res_1", ["Engineer"])

    res = jh_search(job_style="tech jobs", session_id=sid, ticket=tkt)
    # Search tool must not return full job dictionaries
    assert "jobs_preview" not in res.get("data", {})
    assert "jobs" not in res.get("data", {})
    assert "ui_url" in res.get("data", {})


def test_d6_lock_file_and_pid_file(monkeypatch):
    from jh import worker_launcher
    run_dir = worker_launcher.get_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Call start_detached_server with mock Popen
    class MockProc:
        pid = 9876
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: MockProc())
    monkeypatch.setattr(worker_launcher, "is_server_healthy", lambda *a, **kw: False)

    info = worker_launcher.start_detached_server(preferred_port=8999)
    assert info["status"] == "started"
    assert (run_dir / "server.pid").is_file()
    assert (run_dir / "server.lock").is_file()


def test_find_free_port_skips_active_listener_and_rejects_foreign_health():
    import json
    import socket
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading
    from jh import worker_launcher

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        busy_port = srv.getsockname()[1]
        picked = worker_launcher.find_free_port(start_port=busy_port, max_attempts=10)
        assert picked != busy_port

    class _ForeignHealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"status": "ok", "home_dir": "C:/some/other/home"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd_srv = HTTPServer(("127.0.0.1", 0), _ForeignHealthHandler)
    hport = httpd_srv.server_port
    t = threading.Thread(target=httpd_srv.serve_forever, daemon=True)
    t.start()
    try:
        assert worker_launcher.is_server_healthy("127.0.0.1", hport, expected_home="C:/expected/home") is False
    finally:
        httpd_srv.shutdown()
        httpd_srv.server_close()
