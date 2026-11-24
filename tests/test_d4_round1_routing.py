"""Tests for D4: Mandatory Round 1 questions, STOP prompt, and place-based source routing."""
import pytest
from jh import config, db, ticket_manager, interview_questions, pipeline, regions, source_registry
from jh.v5_tools import jh_begin, jh_confirm


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()


def test_d4_round1_stop_prompt_first_line():
    q = interview_questions.build_step_3_target_questions(
        inferred_roles=[{"role": "Software Engineer", "confidence": 0.8}],
        region_guess={"value": "Tunisia", "confidence": 0.9},
        ask_role=False,
    )
    stop_msg = ticket_manager.build_stop_message(q["formatted_text"])
    first_line = stop_msg.splitlines()[0]
    assert first_line == "STOP. Ask the user the questions below and wait for the answer. Do not call another tool."


def test_d4_round1_has_method_place_and_conditional_role():
    # Case 1: high confidence role (ask_role = False)
    q_high = interview_questions.build_step_3_target_questions(
        inferred_roles=[{"role": "Cloud Engineer", "confidence": 0.85}],
        region_guess={"value": "Tunisia", "confidence": 0.9},
        ask_role=False,
    )
    q_ids = [item["id"] for item in q_high["questions"]]
    assert "method" in q_ids
    assert "target_place" in q_ids
    assert "target_role" not in q_ids

    # Case 2: low confidence role (ask_role = True)
    q_low = interview_questions.build_step_3_target_questions(
        inferred_roles=[{"role": "General Candidate", "confidence": 0.3}],
        region_guess={"value": "Tunisia", "confidence": 0.9},
        ask_role=True,
    )
    q_ids_low = [item["id"] for item in q_low["questions"]]
    assert "method" in q_ids_low
    assert "target_place" in q_ids_low
    assert "target_role" in q_ids_low


def test_d4_source_routing_tunisia_excludes_global_remote():
    prefs = {"home_country": "Tunisia"}
    profile = {"location": "Tunis, Tunisia", "work_mode": "Remote"}
    location = "Tunisia"
    
    targets = regions.resolve_targets(prefs, profile, location)
    assert "TN" in targets

    # For Tunisia search, global remote feeds must be excluded
    loc_clean = location.lower().strip()
    is_tunisia = "tn" in targets or loc_clean in ("tunisia", "tunis")
    remote_ok = regions.wants_remote(prefs, profile)
    if is_tunisia:
        remote_ok = False

    # Check that remote-only sources (Jobicy, RemoteOK, Himalayas) are skipped
    global_remote_sources = ["Jobicy", "RemoteOK", "Himalayas", "Remotive", "We Work Remotely"]
    for s_name in global_remote_sources:
        skip = source_registry.skip_reason(s_name, prefs, targets, remote_ok=remote_ok, configured=True)
        assert skip is not None, f"Expected {s_name} to be skipped for Tunisia search"


def test_d4_source_routing_remote_worldwide():
    prefs = {"home_country": "Tunisia"}
    profile = {"location": "Tunis, Tunisia"}
    location = "Remote worldwide"

    targets = regions.resolve_targets(prefs, profile, location)
    # When user asks for Remote worldwide, targets must not be locked to Tunisia local boards
    assert "TN" not in targets
    remote_ok = regions.wants_remote(prefs, profile)
    assert remote_ok is True
