"""Tests for Phase B4: V5 MCP Tools and Guided Flow."""
import os
import pytest

from jh import config, db, v5_tools
from jh.home import get_home


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolate DB and home to a temporary folder for testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_db


def test_jh_start_new_user_and_returning_user():
    # 1. New user (no saved filters)
    res_new = v5_tools.jh_start(prompt="I need a job")
    assert res_new["status"] == "needs_input"
    assert res_new["step"] == 4
    assert res_new["next_tool"] == "jh_set_filters"
    assert "questions" in res_new["options"]
    assert len(res_new["options"]["questions"]) <= 7
    assert res_new["options"]["recommended"]["job_style"] == "tech jobs"

    # 2. Save filters to simulate a returning user
    db.save_view_filters({
        "job_style": "backend systems",
        "roles": ["Backend Engineer"],
        "min_salary": 150000,
        "work_mode": "remote",
        "locations": ["US"]
    })

    # 3. Returning user
    res_ret = v5_tools.jh_start(prompt="hello")
    assert res_ret["status"] == "ok"
    assert res_ret["step"] == 2
    assert "Welcome back" in res_ret["message_for_user"]
    assert res_ret["options"]["choices"] == ["reuse", "edit", "start over"]
    assert res_ret["options"]["recommended"] == "reuse"
    assert res_ret["next_tool"] == "jh_search"


def test_jh_set_filters_and_clash_detection():
    # Test Clash 1: Remote work mode with a single specific city
    res_clash1 = v5_tools.jh_set_filters({
        "job_style": "frontend",
        "work_mode": "remote",
        "locations": ["Chicago, IL"],
        "relocation": False
    })
    assert len(res_clash1["data"]["clashes"]) > 0
    assert "Clash detected: Work mode is 'remote'" in res_clash1["data"]["clashes"][0]

    # Test Clash 2: Extreme salary for junior level
    res_clash2 = v5_tools.jh_set_filters({
        "job_style": "junior developer",
        "seniority": ["junior"],
        "min_salary": 450000
    })
    assert any("above market bands for entry/junior" in c for c in res_clash2["data"]["clashes"])

    # Test Round 2 triggers: Remote triggers time zone; onsite triggers relocation
    res_r2 = v5_tools.jh_set_filters({
        "job_style": "backend",
        "work_mode": "remote",
        "visa_need": True
    })
    assert res_r2["data"]["round_2_triggered"] is True
    r2_qs = res_r2["options"]["round_2_questions"]
    q_ids = [q["id"] for q in r2_qs]
    assert "time_zone" in q_ids
    assert "visa_countries" in q_ids


def test_jh_load_resume_and_confirm_profile():
    # Load raw text resume
    sample_text = """
    Alice Johnson
    Senior Full Stack Engineer
    Skills: Python, TypeScript, React, Docker, AWS, SQL
    Experience: 8 years building cloud applications.
    """
    res_load = v5_tools.jh_load_resume(raw_text=sample_text)
    assert res_load["status"] == "ok"
    assert res_load["step"] == 3
    assert res_load["next_tool"] == "jh_confirm_profile"
    assert "Python" in res_load["data"]["skills"]

    # Confirm profile
    res_conf = v5_tools.jh_confirm_profile(confirmed=True, overrides={"target_title": "Lead Software Architect"})
    assert res_conf["status"] == "ok"
    assert res_conf["step"] == 3
    assert res_conf["next_tool"] == "jh_set_filters"

    # Profile in DB updated
    p = db.get_profile()
    assert p["target_title"] == "Lead Software Architect"


def test_jh_search_blocks_only_missing_job_style():
    # Missing job style blocks with needs_input
    res_block = v5_tools.jh_search(job_style="")
    assert res_block["status"] == "needs_input"
    assert res_block["step"] == 4
    assert res_block["next_tool"] == "jh_search"
    assert "job style is required" in res_block["message_for_user"].lower()

    # With job style provided, search proceeds
    # Populate a fake job first so query_jobs finds it
    db.store_jobs([{
        "id": "job_search_1",
        "title": "Cloud Architect",
        "company": "SkyNet",
        "location": "Remote",
        "work_mode": "Remote",
        "url": "https://example.com/sky",
        "score": 85,
    }])
    res_ok = v5_tools.jh_search(job_style="cloud architect")
    assert res_ok["status"] == "ok"
    assert res_ok["step"] == 7
    assert res_ok["data"]["matches_count"] >= 1


def test_jh_query_and_usable_gate():
    # Store 12 matching jobs to satisfy usable gate [10, 300]
    jobs = [
        {
            "id": f"q_job_{i}",
            "title": f"Security Engineer {i}",
            "company": f"SecCorp {i}",
            "location": "Remote",
            "work_mode": "Remote",
            "url": f"https://example.com/sec/{i}",
            "score": 80 + i,
        }
        for i in range(12)
    ]
    db.store_jobs(jobs)

    res = v5_tools.jh_query()
    assert res["status"] == "ok"
    assert res["step"] == 7
    assert res["data"]["count"] == 12
    assert res["data"]["usable_gate"]["usable"] is True
    assert res["next_tool"] == "jh_open_ui"


def test_jh_open_ui_and_health():
    res = v5_tools.jh_open_ui(port=8765)
    assert res["status"] == "ok"
    assert res["step"] == 8
    assert "http://" in res["data"]["url"]
    assert res["data"]["server_ready"] is True
    assert res["next_tool"] == "jh_status"


def test_jh_status_full_system_state():
    res = v5_tools.jh_status()
    assert res["status"] == "ok"
    assert res["step"] == "status"
    assert "workspace_home" in res["data"]
    assert "radar_state" in res["data"]
    assert "total_jobs" in res["data"]
    assert res["next_tool"] == "jh_search"


def test_jh_feedback_dismissals_and_tuning():
    # 1. Dismiss 4 jobs
    for i in range(4):
        v5_tools.jh_feedback(job_id=f"j_dismiss_{i}", action="dismiss", reason="irreverent")

    # 2. 5th dismissal triggers tuning suggestion
    res5 = v5_tools.jh_feedback(job_id="j_dismiss_4", action="dismiss", reason="bad culture", exclude_company="BadCo", exclude_keyword="crypto")
    assert res5["status"] == "ok"
    assert res5["step"] == 10
    assert res5["data"]["tuning_suggestion"] is not None
    assert "dismissed 5 jobs" in res5["data"]["tuning_suggestion"]
    assert "BadCo" in res5["data"]["excluded_companies"]
    assert "crypto" in res5["data"]["excluded_keywords"]
