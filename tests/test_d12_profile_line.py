"""Tests for D12: Structured profile line in jh_begin and post-launch 1-liner summary.
"""
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_begin, jh_launch

SAMPLE_RESUME = """Rayen Ben Aissa
rayen@example.com | +216 20 123 456 | Tunis, Tunisia
linkedin.com/in/rayenba | github.com/rayenba

Cloud / Software Engineering Intern (2027 Start)

SUMMARY
Computer Science student and intern with experience in Cloud computing, Python, Docker, AWS, and REST APIs.

SKILLS
Python, Docker, AWS, FastAPI, Git, Linux, SQL, REST APIs

EXPERIENCE
Software Engineering Intern, Vermeg, Tunis, Tunisia
Jun 2024 - Aug 2024
- Built a microservice in Python and Docker deployed to AWS ECS.
- Automated API unit tests with GitHub Actions.

EDUCATION
Bachelor of Science in Computer Science, INSAT, 2027
"""


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d12_jh_begin_returns_profile_line():
    sid = "test_d12_prof"
    res = jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    assert res["status"] in ("needs_target", "needs_role")
    assert "profile_line" in res
    assert "profile_line" in res["data"]
    line = res["profile_line"]
    assert "Rayen Ben Aissa" in line
    assert "Roles:" in line
    assert "Exp:" in line
    assert "Top Skills:" in line
    assert "Tell me if this is wrong" in line
    # Profile line appears right before questions in message_for_user
    assert line in res["message_for_user"]


def test_d12_jh_launch_returns_concise_launch_summary(monkeypatch):
    from jh import worker_launcher
    monkeypatch.setattr(worker_launcher, "start_background_search", lambda *a, **kw: {"search_job_id": "s_123", "status": "started"})

    sid = "test_d12_launch"
    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.ANSWERED)
    tkt = ticket_manager.generate_ticket(sid, "res_1", ["Engineer"])

    launch_res = jh_launch(session_id=sid, ticket=tkt)
    assert launch_res["status"] == "ok"
    assert launch_res["search_status"] in ("started", "already_running")
    assert launch_res["data"]["method"] == "hybrid"
