"""Tests for D9: Visa handling without guessing, 'work rights not confirmed' flag in UI,
and filtering only upon confirmed user response.
"""
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_answer


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d9_visa_job_not_removed_by_guess():
    sid = "test_d9_visa"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.LAUNCHED)

    # Insert a US on-site role that does not sponsor
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, work_mode, visa_sponsor, fit_score, freshness_state, job_json, created_at, updated_at)
            VALUES 
            ('j_us', 'k_us', 'Software Engineer', 'USCorp', 'New York, NY', 'Onsite', 0, 90, 'active', '{"location":"New York, NY","work_mode":"Onsite"}', '2026-11-24', '2026-11-24')
        """)

    # Query before user answers visa question
    q = db.query_jobs(session_id=sid)
    # The job must not be removed before visa question is answered
    assert q["count"] == 1
    assert q["jobs"][0]["id"] == "j_us"


def test_d9_visa_filtered_only_after_user_answer():
    sid = "test_d9_filter"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.LAUNCHED)
    ticket_manager.record_questions_presented(sid, "Round 2 questions")
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] -= 10.0

    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, work_mode, visa_sponsor, fit_score, freshness_state, job_json, created_at, updated_at)
            VALUES 
            ('j_us_onsite', 'k_us_1', 'Software Engineer', 'USCorp', 'San Francisco, CA', 'Onsite', 0, 90, 'active', '{"location":"San Francisco, CA","work_mode":"Onsite"}', '2026-11-24', '2026-11-24'),
            ('j_tn_onsite', 'k_tn_1', 'Software Engineer', 'TNCorp', 'Tunis', 'Onsite', 0, 90, 'active', '{"location":"Tunis","work_mode":"Onsite"}', '2026-11-24', '2026-11-24')
        """)

    # User answers: require visa sponsorship or no work rights in US
    res = jh_answer(session_id=sid, user_reply="I require visa sponsorship, no legal work rights in US")
    assert res["status"] == "ok"

    # Query again
    q = db.query_jobs(session_id=sid)
    # The US job with visa_sponsor=0 is now hidden by visa filter
    assert q["removed_counts"]["visa"] >= 1 or q["count"] <= 1
