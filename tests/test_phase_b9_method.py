"""Tests for Phase B9: Method choice (Modern vs Classic), proof points, and guided interview routing."""
import os
import pytest

from jh import config, db
from jh.v5_tools import jh_confirm_profile, jh_set_method, jh_start, jh_status


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    # Reset method to modern
    config.set_method("modern")
    return test_home


def test_default_method_is_modern():
    assert config.get_method() == "modern"
    status = jh_status()
    assert status["data"]["method"] == "modern"
    assert "Modern (Outreach First)" in status["message_for_user"]


def test_jh_set_method_switching_and_preservation():
    # Insert a dummy job and profile
    db.save_profile({
        "target_title": "Backend Lead",
        "skills": ["Go", "Kubernetes"],
    }, profile_id="master")

    # Switch to Classic
    res_classic = jh_set_method("classic")
    assert res_classic["status"] == "ok"
    assert res_classic["data"]["method"] == "classic"
    assert config.get_method() == "classic"

    # Status shows Classic
    status_classic = jh_status()
    assert status_classic["data"]["method"] == "classic"
    assert "Classic (Job Boards" in status_classic["message_for_user"]

    # Profile data preserved
    p = db.get_profile()
    assert p["target_title"] == "Backend Lead"

    # Switch back to Modern
    res_modern = jh_set_method("modern")
    assert res_modern["status"] == "ok"
    assert res_modern["data"]["method"] == "modern"
    assert config.get_method() == "modern"


def test_jh_start_switch_method_intent():
    res = jh_start(prompt="I want to switch method")
    assert res["status"] == "needs_input"
    assert res["step"] == "method_choice"
    assert res["next_tool"] == "jh_set_method"
    assert "classic" in res["options"]["choices"]
    assert "modern" in res["options"]["choices"]


def test_confirm_profile_collects_portfolio_and_proof_points():
    proofs = [
        {"project": "High-throughput pipeline", "metric": "Processed 2B events/day", "link": "https://github.com/test/pipeline"},
        {"project": "Search microservice", "metric": "Reduced p99 latency by 50%", "link": "https://github.com/test/search"},
    ]
    res = jh_confirm_profile(
        confirmed=True,
        portfolio_url="https://janedoe.dev",
        proof_points=proofs,
        profile_id="master"
    )
    assert res["status"] == "ok"
    assert res["next_tool"] == "jh_set_method"
    assert res["options"]["recommended"] == "modern"
    assert "Portfolio: https://janedoe.dev" in res["message_for_user"]
    assert "2 recorded" in res["message_for_user"]

    # Verify stored in DB
    prof = db.get_profile("master")
    assert prof["portfolio_url"] == "https://janedoe.dev"
    assert len(prof["proof_points"]) == 2
    assert prof["proof_points"][0]["project"] == "High-throughput pipeline"


def test_modern_interview_questions_in_jh_start():
    # Save a profile so it proceeds to interview
    db.save_profile({
        "target_title": "Staff ML Engineer",
        "skills": ["PyTorch", "Transformers"],
    }, profile_id="master")

    config.set_method("modern")
    res = jh_start(prompt="find me a job")
    assert res["status"] == "needs_input"
    assert res["options"]["method"] == "modern"
    q_ids = [q["id"] for q in res["options"]["questions"]]
    assert "target_role" in q_ids
    assert "region" in q_ids
    assert "stage" in q_ids
    assert "min_salary" in q_ids
    assert "visa_need" in q_ids
    assert "work_mode" in q_ids


def test_classic_interview_questions_in_jh_start():
    db.save_profile({
        "target_title": "Frontend Engineer",
        "skills": ["React", "TypeScript"],
    }, profile_id="master")

    config.set_method("classic")
    res = jh_start(prompt="find me a job")
    assert res["status"] == "needs_input"
    assert res["options"]["method"] == "classic"
    q_ids = [q["id"] for q in res["options"]["questions"]]
    assert "job_style" in q_ids
    assert "work_mode" in q_ids
    assert "locations" in q_ids
