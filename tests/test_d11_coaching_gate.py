"""Tests for D11: Unprompted coaching suppression and explicit-only trigger.
"""
import pytest
from jh import config, db, ticket_manager
from jh.coach import evaluate_coaching


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d11_normal_reply_generates_no_coaching():
    # Ordinary user reply answering questions should produce no coaching envelope
    coaching = evaluate_coaching("I want remote software engineering jobs in Tunisia", session_id="test_d11")
    assert coaching is None


def test_d11_explicit_coaching_request_returns_advice():
    # User explicitly asking for advice / coaching
    coaching = evaluate_coaching("give me advice on how to improve my applications", session_id="test_d11_advice")
    assert coaching is not None
    assert "trigger_id" in coaching or "content" in coaching
