"""Tests for D2: user_reply validation, 5s delay check, audit log, and skip handling."""
import time
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_confirm, jh_answer, jh_set_filters


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    # Reset in-memory sessions
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d2_reject_empty_user_reply():
    sid = "test_d2_empty"
    ticket_manager.record_questions_presented(sid, "Question 1: Method? Question 2: Place?")
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] = time.time() - 6.0
    res = jh_confirm(session_id=sid, user_reply="")
    assert res["status"] == "needs_input"
    assert "empty" in str(res["message_for_user"]).lower() or "empty" in str(res.get("data", {}))


def test_d2_reject_short_user_reply():
    sid = "test_d2_short"
    ticket_manager.record_questions_presented(sid, "Question 1: Method? Question 2: Place?")
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] = time.time() - 6.0
    res = jh_confirm(session_id=sid, user_reply="a")
    assert res["status"] == "needs_input"
    assert "under 2 characters" in str(res["message_for_user"]).lower() or "under 2" in str(res.get("data", {}))


def test_d2_reject_question_echo():
    sid = "test_d2_echo"
    q_text = "STOP. Ask the user the questions below\n1) Method: Modern (default) or Classic\n2) Target place: Tunisia, remote worldwide"
    ticket_manager.record_questions_presented(sid, q_text)
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] = time.time() - 6.0
    res = jh_confirm(session_id=sid, user_reply=q_text)
    assert res["status"] == "needs_input"
    assert "repeats the question" in str(res["message_for_user"]).lower() or "repeats" in str(res.get("data", {}))


def test_d2_reject_too_fast_reply():
    sid = "test_d2_fast"
    ticket_manager.record_questions_presented(sid, "Question 1: Method? Question 2: Place?")
    # Reply immediately (< 5s)
    res = jh_confirm(session_id=sid, user_reply="Modern, Tunisia")
    assert res["status"] == "needs_input"
    assert "too fast" in str(res["message_for_user"]).lower() or "too fast" in str(res.get("data", {}))


def test_d2_valid_reply_stored_in_audit_log():
    sid = "test_d2_audit"
    ticket_manager.record_questions_presented(sid, "Question 1: Method? Question 2: Place?")
    # Artificially set presented_at to 6 seconds ago
    sess = ticket_manager.get_or_create_session(sid)
    sess["questions_presented_at"] = time.time() - 6.0
    sess["resume_id"] = "res_123"

    res = jh_confirm(session_id=sid, user_reply="Modern, Tunisia")
    assert res["status"] in ("ready", "ok")

    logs = db.get_audit_events(sid)
    assert len(logs) >= 1
    assert logs[0]["user_reply"] == "Modern, Tunisia"
    assert logs[0]["action"] == "jh_confirm"


def test_d2_explicit_skips():
    assert ticket_manager.is_explicit_skip("skip") is True
    assert ticket_manager.is_explicit_skip("any") is True
    assert ticket_manager.is_explicit_skip("skip all") is True
    assert ticket_manager.is_explicit_skip("I don't care maybe") is False
    assert ticket_manager.is_explicit_skip("") is False


def test_d2_direct_filter_write_refused():
    sid = "test_d2_direct"
    res = jh_set_filters({"work_mode": "remote"}, session_id=sid)
    assert res["status"] == "needs_input"
    assert "jh_answer" in str(res["message_for_user"]) or "jh_confirm" in str(res["message_for_user"])
