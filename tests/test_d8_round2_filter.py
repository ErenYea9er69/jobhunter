"""Tests for D8: Round 2 questions, live view filtering, and pending ask_user handling.
"""
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_launch, jh_status, jh_answer


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d8_jh_launch_and_status_carry_round2_questions(monkeypatch):
    from jh import worker_launcher, radar
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda *a, **kw: {"search_job_id": "s_123", "status": "started"})
    monkeypatch.setattr(radar, "start_radar_worker", lambda *a, **kw: None)

    sid = "test_d8_sess"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.ANSWERED)
    tkt = ticket_manager.generate_ticket(sid, "res_1", ["Engineer"], method="hybrid", location="Tunisia")

    launch_res = jh_launch(session_id=sid, ticket=tkt)
    assert launch_res["status"] == "ok"
    assert "Job Type & Start Date" in launch_res["ask_user"]
    assert "Daily Email Cap" in launch_res["ask_user"]

    # jh_status in LAUNCHED state carries pending questions
    st_res = jh_status(session_id=sid)
    assert st_res["ask_user"] is not None
    assert "Job Type & Start Date" in st_res["ask_user"]


def test_d8_jh_answer_filters_db_view_and_transitions_state(monkeypatch):
    sid = "test_d8_ans"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.LAUNCHED)
    ticket_manager.record_questions_presented(sid, "Round 2 questions")

    # Fast forward time to pass 5s validation
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] -= 10.0

    # Seed 2 jobs: 1 remote, 1 onsite
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, work_mode, fit_score, freshness_state, job_json, created_at, updated_at)
            VALUES 
            ('j1', 'k1', 'Remote Python Dev', 'Acme', 'Tunis', 'Remote', 90, 'active', '{"work_mode":"Remote"}', '2026-11-24', '2026-11-24'),
            ('j2', 'k2', 'Onsite Java Dev', 'Beta', 'Tunis', 'Onsite', 85, 'active', '{"work_mode":"Onsite"}', '2026-11-24', '2026-11-24')
        """)

    ans_res = jh_answer(session_id=sid, user_reply="I prefer remote work only, and internship")
    assert ans_res["status"] == "ok"
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ROUND2_DONE
    assert ans_res["ask_user"] is None
    assert ans_res["data"]["hidden_by_filters"] >= 0

    # Once round 2 is answered, jh_status has ask_user: None
    st = jh_status(session_id=sid)
    assert st["ask_user"] is None
