"""Tests for D5: Modern vs Classic method branching in session, launch, and switching."""
import pytest
from jh import config, db, ticket_manager, radar
from jh.v5_tools import jh_confirm, jh_launch, jh_set_method


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d5_modern_method_launches_radar_and_points_to_signals(monkeypatch):
    sid = "test_d5_modern"
    sess = ticket_manager.get_or_create_session(sid)
    sess["resume_id"] = "res_123"
    sess["session_state"] = ticket_manager.SessionState.ANSWERED
    sess["method"] = "modern"
    ticket = ticket_manager.generate_ticket(sid, "res_123", ["Cloud Engineer"], method="modern")

    # Mock server, radar, and background search start
    radar_started = []
    board_search_started = []
    monkeypatch.setattr(radar, "start_radar_worker", lambda: radar_started.append(True))

    from jh import worker_launcher
    monkeypatch.setattr(worker_launcher, "start_detached_server", lambda preferred_port=8080: {"status": "started", "port": 8080, "pid": 1234})
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda **kw: board_search_started.append(kw) or {"search_job_id": "board_123", "status": "started"})

    res = jh_launch(session_id=sid, ticket=ticket)
    assert res["status"] == "ok"
    assert "#/signals" in res["ui_url"]
    assert len(radar_started) >= 1
    assert len(board_search_started) == 1
    assert res["data"]["board_search_job_id"] == "board_123"


def test_d5_classic_method_launches_board_search_and_points_to_jobs(monkeypatch):
    sid = "test_d5_classic"
    sess = ticket_manager.get_or_create_session(sid)
    sess["resume_id"] = "res_123"
    sess["session_state"] = ticket_manager.SessionState.ANSWERED
    sess["method"] = "classic"
    ticket = ticket_manager.generate_ticket(sid, "res_123", ["Cloud Engineer"], method="classic")

    board_search_started = []
    from jh import worker_launcher
    monkeypatch.setattr(worker_launcher, "start_detached_server", lambda preferred_port=8080: {"status": "started", "port": 8080, "pid": 1234})
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda **kw: {"search_job_id": "job_123", "status": "started"})

    res = jh_launch(session_id=sid, ticket=ticket)
    assert res["status"] == "ok"
    assert "#/jobs" in res["ui_url"]


def test_d5_switch_method_preserves_data_and_switches_session():
    sid = "test_d5_switch"
    res1 = jh_set_method("modern", session_id=sid)
    assert res1["status"] == "ok"
    assert res1["data"]["method"] == "modern"

    res2 = jh_set_method("classic", session_id=sid)
    assert res2["status"] == "ok"
    assert res2["data"]["method"] == "classic"
