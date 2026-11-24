"""Tests for D3: Guesses vs Answers storage split, confidence threshold >= 0.5 for roles, and guess isolation."""
import pytest
from jh import config, db, ticket_manager
from jh.v5_tools import jh_begin, jh_confirm


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d3_storage_split_guesses_and_answers():
    sid = "test_d3_split"
    # Store guesses from inference
    db.store_guess(sid, "role", "Cloud Engineer", confidence=0.85)
    db.store_guess(sid, "role", "Junior Developer", confidence=0.35)
    db.store_guess(sid, "location", "Tunis, Tunisia", confidence=0.7)
    db.store_guess(sid, "job_type", "Internship", confidence=0.9)
    db.store_guess(sid, "pay", "30000", confidence=0.4)

    guesses = db.get_guesses(sid)
    assert len(guesses) == 5
    assert db.get_answers(sid) == []

    # Store user answer
    db.store_answer(sid, "method", "modern", user_reply="Modern, Tunisia")
    db.store_answer(sid, "target_place", "Tunisia", user_reply="Modern, Tunisia")

    answers = db.get_answers(sid)
    assert len(answers) == 2
    assert db.get_confirmed_answer(sid, "target_place") == "Tunisia"
    assert db.get_confirmed_answer(sid, "job_type") is None


def test_d3_role_confidence_threshold_05():
    sid = "test_d3_roles"
    db.store_guess(sid, "role", "High Confidence Role", confidence=0.75)
    db.store_guess(sid, "role", "Low Confidence Role", confidence=0.40)

    role_guesses = db.get_guesses(sid, category="role")
    scope_roles = [r["value"] for r in role_guesses if r["confidence"] >= 0.5]
    assert "High Confidence Role" in scope_roles
    assert "Low Confidence Role" not in scope_roles


def test_d3_guessed_location_never_filters_before_answer():
    sid = "test_d3_no_filter"
    # Given a guessed location
    db.store_guess(sid, "location", "Tunis, Tunisia", confidence=0.8)
    
    # Confirmed location answer must be None
    assert db.get_confirmed_answer(sid, "target_place") is None
    # Guessed location must not be in answers
    confirmed = [a["value"] for a in db.get_answers(sid, category="target_place")]
    assert len(confirmed) == 0
