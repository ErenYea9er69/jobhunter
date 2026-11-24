"""Tests for D7: Chromium launch with extension, /api/ping endpoint, and ui_seen tracking.
"""
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_launch, jh_status


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d7_launch_carries_browser_and_ui_seen_fields(monkeypatch):
    from jh import worker_launcher
    monkeypatch.setattr(worker_launcher, "start_detached_server", lambda *a, **kw: {"status": "started", "port": 8888})
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda *a, **kw: {"search_job_id": "s_123", "status": "started"})
    monkeypatch.setattr(worker_launcher, "open_browser", lambda *a, **kw: True)

    sid = "test_d7_launch"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.ANSWERED)
    tkt = ticket_manager.generate_ticket(sid, "res_1", ["Engineer"])

    res = jh_launch(session_id=sid, ticket=tkt)
    assert res["status"] == "ok"
    assert res["browser_opened"] is True
    assert res["ui_seen"] is False  # UI has not pinged yet
    assert "extension_status" in res
    assert "data" in res
    assert res["data"]["browser_opened"] is True
    assert res["data"]["ui_seen"] is False

    # Simulate /api/ping from browser
    sess = ticket_manager.get_or_create_session(sid)
    sess["ui_seen"] = True

    # Now status reflects ui_seen: True
    st = jh_status(session_id=sid)
    assert st["data"]["ui_seen"] is True
