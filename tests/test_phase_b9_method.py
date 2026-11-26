"""Tests for Phase B9: Hybrid-only method consolidation, proof points, and guided criteria."""
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
    config.set_method("hybrid")
    return test_home


def test_default_method_is_hybrid():
    assert config.get_method() == "hybrid"
    assert config.method_uses_modern() is True
    assert config.method_uses_classic() is True
    status = jh_status()
    assert status["data"]["method"] == "hybrid"
    assert "Hybrid" in status["message_for_user"]


def test_jh_set_method_keeps_hybrid_and_preserves_profile():
    db.save_profile({"target_title": "Backend Lead", "skills": ["Go", "Kubernetes"]}, profile_id="master")
    res = jh_set_method("classic")
    assert res["status"] == "ok"
    assert res["data"]["method"] == "hybrid"
    assert config.get_method() == "hybrid"
    p = db.get_profile()
    assert p["target_title"] == "Backend Lead"


def test_confirm_profile_collects_portfolio_and_proof_points():
    proofs = [
        {"project": "High-throughput pipeline", "metric": "Processed 2B events/day", "link": "https://github.com/test/pipeline"},
        {"project": "Search microservice", "metric": "Reduced p99 latency by 50%", "link": "https://github.com/test/search"},
    ]
    res = jh_confirm_profile(
        confirmed=True,
        portfolio_url="https://janedoe.dev",
        proof_points=proofs,
        profile_id="master",
    )
    assert res["status"] == "ok"
    assert res["options"]["recommended"] == "hybrid"
    assert "Portfolio: https://janedoe.dev" in res["message_for_user"]
    assert "2 recorded" in res["message_for_user"]

    prof = db.get_profile("master")
    assert prof["portfolio_url"] == "https://janedoe.dev"
    assert len(prof["proof_points"]) == 2
    assert prof["proof_points"][0]["project"] == "High-throughput pipeline"


def test_hybrid_interview_questions_in_jh_start():
    db.save_profile({"target_title": "Staff ML Engineer", "skills": ["PyTorch", "Transformers"]}, profile_id="master")
    res = jh_start(prompt="find me a job")
    assert res["status"] == "needs_input"
    assert res["options"]["method"] == "hybrid"
    q_ids = [q["id"] for q in res["options"]["questions"]]
    assert "target_role" in q_ids
    assert "region" in q_ids
    assert "stage" in q_ids
    assert "min_salary" in q_ids
    assert "visa_need" in q_ids
    assert "work_mode" in q_ids
