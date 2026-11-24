"""Tests for D1: Rigid Session State Machine (NEW, RESUME_OK, ASKED, ANSWERED, LAUNCHED, ROUND2_DONE)
and enforcement across all tools and old aliases.
"""
import time
import pytest
from jh import config, db, ticket_manager
from jh.ticket_manager import SessionState
from jh.v5_tools import jh_begin, jh_confirm, jh_launch, jh_search
from jh.mcp_tools import register_tools_and_resources
from jh.filestore import OutputStore
from mcp.server.fastmcp import FastMCP


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d1_initial_state_is_new():
    sid = "test_d1_new"
    state = ticket_manager.get_session_state_name(sid)
    assert state == SessionState.NEW


def test_d1_out_of_order_search_refused_in_new_or_asked():
    sid = "test_d1_refuse_search"
    # In NEW state, jh_search must be refused
    res = jh_search(query="python developer", session_id=sid)
    assert res["status"] == "needs_input"
    assert "jh_begin" in res["next_tool"] or "resume" in str(res["message_for_user"]).lower()

    # Move to ASKED state
    ticket_manager.transition_session_state(sid, SessionState.ASKED)
    res2 = jh_search(query="python developer", session_id=sid)
    assert res2["status"] == "needs_input"
    assert res2["next_tool"] == "jh_confirm"


def test_d1_jh_launch_refused_without_answered_state_and_ticket():
    sid = "test_d1_launch_gate"
    # In NEW or ASKED state, jh_launch refused
    res = jh_launch(session_id=sid, ticket="")
    assert res["status"] == "needs_input"

    # In ASKED state with fake ticket, still refused
    ticket_manager.transition_session_state(sid, SessionState.ASKED)
    res2 = jh_launch(session_id=sid, ticket="fake_ticket")
    assert res2["status"] == "needs_input"
    assert res2["next_tool"] == "jh_confirm"


def test_d1_full_state_lifecycle():
    sid = "test_d1_lifecycle"
    # 1. NEW
    assert ticket_manager.get_session_state_name(sid) == SessionState.NEW

    # 2. Provide resume via jh_begin -> transitions to ASKED (returns Round 1 questions, never auto-ticket)
    sample_resume = (
        "Rayen Ben Aissa\n"
        "Email: rayen.benaissa@email.com | Phone: +216 12 345 678 | Tunis, Tunisia\n"
        "LinkedIn: linkedin.com/in/rayenbenaissa | GitHub: github.com/rayenbenaissa\n\n"
        "SUMMARY\n"
        "Motivated Software Engineering student seeking a Cloud, Backend, or Full Stack Software Engineering Internship. "
        "Experienced with AWS, C#, Express, Python, JavaScript, Docker, and SQL databases.\n\n"
        "SKILLS\n"
        "Languages: Python, JavaScript, TypeScript, C#, SQL\n"
        "Technologies: AWS, Docker, CI/CD, Linux, FastAPI, Node.js, Express, PostgreSQL, MongoDB, React\n\n"
        "EDUCATION\n"
        "Higher Institute of Computer Science (ISI), Tunis\n"
        "Bachelor of Science in Computer Science (2024 - 2027)\n\n"
        "PROJECTS\n"
        "Cloud Deployment Pipeline: Built automated CI/CD pipeline using Docker and AWS Lambda.\n"
        "Web Application: Full-stack application with FastAPI backend and PostgreSQL database.\n"
    )
    res1 = jh_begin(resume_text=sample_resume, session_id=sid)
    assert res1["status"] in ("needs_target", "needs_role")
    assert ticket_manager.get_session_state_name(sid) == SessionState.ASKED
    assert res1.get("ticket") is None  # Must NOT issue ticket before questions answered!

    # 3. Answer Round 1 questions via jh_confirm -> transitions to ANSWERED, ticket issued
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] = time.time() - 6.0
    res2 = jh_confirm(session_id=sid, user_reply="Modern, Tunisia")
    assert res2["status"] == "ready"
    assert res2.get("ticket") is not None
    assert ticket_manager.get_session_state_name(sid) == SessionState.ANSWERED
    ticket = res2["ticket"]

    # 4. jh_launch with valid ticket -> transitions to LAUNCHED
    res3 = jh_launch(session_id=sid, ticket=ticket)
    assert res3["status"] == "ok"
    assert ticket_manager.get_session_state_name(sid) == SessionState.LAUNCHED
