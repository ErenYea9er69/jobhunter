"""Tests for D5: Hybrid-only method consolidation across session, launch, and settings."""
from jh import config, db, ticket_manager, radar
from jh.v5_tools import jh_launch, jh_set_method


def test_d5_hybrid_method_runs_radar_and_board_search(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()

    sid = "test_d5_hybrid"
    sess = ticket_manager.get_or_create_session(sid)
    sess["resume_id"] = "res_123"
    sess["session_state"] = ticket_manager.SessionState.ANSWERED
    ticket = ticket_manager.generate_ticket(sid, "res_123", ["Cloud Engineer"], method="hybrid")

    radar_started = []
    board_search_started = []
    monkeypatch.setattr(radar, "start_radar_worker", lambda: radar_started.append(True))

    from jh import worker_launcher
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda **kw: board_search_started.append(kw) or {"search_job_id": "board_123", "status": "started"})

    res = jh_launch(session_id=sid, ticket=ticket)
    assert res["status"] == "ok"
    assert res["data"]["method"] == "hybrid"
    assert len(radar_started) >= 1
    assert len(board_search_started) == 1


def test_d5_set_method_normalizes_all_requests_to_hybrid(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()

    for req in ("modern", "classic", "hybrid", "unknown"):
        res = jh_set_method(req, session_id="test_d5_norm")
        assert res["status"] == "ok"
        assert res["data"]["method"] == "hybrid"
        assert config.get_method() == "hybrid"
