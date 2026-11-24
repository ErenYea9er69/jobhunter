"""Step 3 Adversarial Test Suite for JobHunter V7.

Tests aggressive attempts to bypass the Ask-First flow:
1. Sends resume and attempts to search without answering questions.
2. Answers in under 2 seconds.
3. Echoes questions back as the answer.
4. Calls jh_launch with a ticket from another session, an expired ticket, or no ticket.
5. Calls tailor_resume, cover_letter, outreach_message on an unsaved job.
6. Calls old tool names directly (search_jobs, jh_search, query_jobs, jh_query).

Every trick must be refused with status 'needs_input' or 'not_saved', and must carry pending questions.
"""
import asyncio
import json
import time
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_begin, jh_confirm, jh_launch, jh_search, jh_query

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
    test_db = tmp_path / "test_adversarial.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_adv_1_search_before_questions_refused():
    sid = "adv_sess_1"
    begin_res = jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    assert begin_res["status"] in ("needs_target", "needs_role")
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ASKED

    # Adversary tries to call jh_search immediately without answering questions
    search_res = jh_search(job_style="Cloud Engineer", session_id=sid)
    assert search_res["status"] == "needs_input"
    assert search_res["next_tool"] == "jh_confirm"
    assert "STOP" in search_res["message_for_user"]
    assert search_res["ask_user"] is not None


def test_adv_2_reply_under_2_seconds_refused():
    sid = "adv_sess_2"
    begin_res = jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    assert begin_res["status"] in ("needs_target", "needs_role")

    # Reply arrives 0.5s after questions (< 5.0s minimum threshold)
    confirm_res = jh_confirm(session_id=sid, user_reply="Modern method, Tunisia, Cloud Engineer")
    assert confirm_res["status"] == "needs_input"
    assert "too fast" in confirm_res["data"]["error"]
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ASKED


def test_adv_3_question_echo_refused():
    sid = "adv_sess_3"
    begin_res = jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    sess = ticket_manager.get_or_create_session(sid)
    # Simulate elapsed time > 5s
    sess["questions_presented_at"] -= 10.0

    # Adversary echoes questions back verbatim
    q_echo = begin_res["ask_user"]
    confirm_res = jh_confirm(session_id=sid, user_reply=q_echo)
    assert confirm_res["status"] == "needs_input"
    assert "repeats the questions" in confirm_res["data"]["error"]
    assert ticket_manager.get_session_state_name(sid) == ticket_manager.SessionState.ASKED


def test_adv_4_launch_ticket_forgery_refused():
    sid = "adv_sess_4"
    other_sid = "adv_other_sess"

    # 1. No ticket
    res_no_tkt = jh_launch(session_id=sid, ticket="")
    assert res_no_tkt["status"] == "needs_input"

    # 2. Fake ticket
    res_fake = jh_launch(session_id=sid, ticket="jh_tkt_0000000000000000")
    assert res_fake["status"] == "needs_input"

    # 3. Ticket issued for another session
    ticket_manager.transition_session_state(other_sid, ticket_manager.SessionState.ANSWERED)
    other_tkt = ticket_manager.generate_ticket(other_sid, "res_other", ["Engineer"])

    ticket_manager.transition_session_state(sid, ticket_manager.SessionState.ANSWERED)
    res_mismatch = jh_launch(session_id=sid, ticket=other_tkt)
    assert res_mismatch["status"] == "needs_input"
    assert "ticket was issued for session" in res_mismatch["data"]["error"]

    # 4. Expired ticket (> 2 hours)
    expired_tkt = ticket_manager.generate_ticket(sid, "res_4", ["Engineer"])
    ticket_manager._TICKETS[expired_tkt]["expires_at"] = time.time() - 100.0
    res_exp = jh_launch(session_id=sid, ticket=expired_tkt)
    assert res_exp["status"] == "needs_input"
    assert "expired" in res_exp["data"]["error"]


def test_adv_5_tailor_and_outreach_on_unsaved_job_refused(tmp_path):
    import mcp_server

    # Create job in database with saved_by = '' (not saved via UI)
    with db.session() as c:
        c.execute("""
            INSERT INTO jobs (id, job_key, title, company, location, freshness_state, job_json, created_at, updated_at, saved_by)
            VALUES ('job_adv_unsaved', 'k_adv_u', 'Cloud Architect', 'MegaCorp', 'Tunis', 'active', '{}', '2026-11-24', '2026-11-24', '')
        """)

    srv = mcp_server.create_server(str(tmp_path))

    def call_tool(name, **kwargs):
        res = asyncio.run(srv.call_tool(name, kwargs))
        blocks = res[0] if isinstance(res, tuple) else res
        return json.loads(blocks[0].text)

    # Attempt tailor_resume on unsaved job
    t_res = call_tool("tailor_resume", job_id="job_adv_unsaved")
    assert t_res["data"]["status"] == "not_saved"
    assert t_res["data"]["success"] is False

    # Attempt cover_letter on unsaved job
    c_res = call_tool("cover_letter", job_id="job_adv_unsaved")
    assert c_res["data"]["status"] == "not_saved"
    assert c_res["data"]["success"] is False

    # Attempt outreach_message on unsaved job
    o_res = call_tool("outreach_message", job_id="job_adv_unsaved")
    assert o_res["data"]["status"] == "not_saved"
    assert o_res["data"]["success"] is False


def test_adv_6_old_tool_names_refused_in_uninitialized_state(tmp_path):
    import mcp_server

    srv = mcp_server.create_server(str(tmp_path))

    def call_tool(name, **kwargs):
        res = asyncio.run(srv.call_tool(name, kwargs))
        blocks = res[0] if isinstance(res, tuple) else res
        return json.loads(blocks[0].text)

    # Fresh session in state NEW: search_jobs must be refused
    s_res = call_tool("search_jobs", query="DevOps")
    assert s_res["data"]["status"] == "needs_input"
    assert "requires a loaded resume" in s_res["data"]["message_for_user"]
