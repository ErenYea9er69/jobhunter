"""UX audit tests: intake completeness, preference sync, score recalculation, tailoring alignment, and team-surface flow."""
from __future__ import annotations

import asyncio
import datetime
import json
from unittest.mock import patch

import pytest

import mcp_server
from conftest import SAMPLE_RESUME
from jh import config, db, interview_questions, pipeline, preferences, radar, ticket_manager, v5_tools, worker_launcher


@pytest.fixture(autouse=True)
def isolated_ux_env(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    resumes_dir = ws / "resumes"
    resumes_dir.mkdir(exist_ok=True)
    (resumes_dir / "ahmed.txt").write_text(SAMPLE_RESUME, encoding="utf-8")

    home_dir = tmp_path / "jobmcp_home"
    data_dir = home_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("JOBMCP_HOME", str(home_dir))
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(config, "DB_PATH", str(data_dir / "state"))
    preferences._cache.update(mtime=None, path=None, data=None)

    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    monkeypatch.setattr(radar, "start_radar_worker", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline, "search", lambda *a, **kw: {"jobs": [], "total": 0, "statuses": []})
    return {"ws": ws, "home": home_dir, "data": data_dir}


def test_round2_intake_covers_core_job_preferences_without_ui_or_outreach_clutter():
    r2 = interview_questions.build_round_2_questions(
        profile={"target_title": "Backend Engineer"},
        job_type_guess={"value": "full-time"},
        region_guess={"value": "Europe"},
    )
    q_ids = [q["id"] for q in r2["questions"]]
    assert q_ids == ["target_role", "work_mode", "job_type", "pay", "visa", "company_type"]
    assert "daily_email_cap" not in q_ids
    assert "voice_samples" not in q_ids
    assert "in the ui" not in r2["formatted_text"].lower()


def test_answers_sync_to_preferences_rescore_jobs_and_drive_tailoring(isolated_ux_env):
    sid = "ux_sync_sess"
    b = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    assert b["status"] in ("needs_target", "needs_role")

    c = v5_tools.jh_confirm(session_id=sid, user_reply="France, target role DevOps Engineer")
    assert c["status"] == "ready"
    assert c["data"]["role_focus"] == ["DevOps Engineer"]
    assert "Method=" not in c["message_for_user"]

    v5_tools.jh_launch(session_id=sid, ticket=c["ticket"])

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.store_jobs([
        {
            "id": "job_remote_devops",
            "title": "DevOps Engineer",
            "company": "CloudScale",
            "location": "Paris, France",
            "country": "France",
            "work_mode": "Remote",
            "job_type": "full-time",
            "languages": ["English"],
            "salary": "95000 EUR",
            "description": "Docker, AWS, CI/CD, Python automation.",
            "posted_at": now_iso,
        },
        {
            "id": "job_onsite_django",
            "title": "Software Engineer",
            "company": "WebShop",
            "location": "Paris, France",
            "country": "France",
            "work_mode": "Onsite",
            "job_type": "internship",
            "salary": "30000 EUR",
            "description": "Onsite Django internship.",
            "posted_at": now_iso,
        },
    ], query="Engineer")

    # User updates roles, work mode, job type, min salary, languages & exclusions
    ans = v5_tools.jh_answer(
        session_id=sid,
        user_reply="Target role DevOps Engineer, remote, full-time, at least 80000, exclude php",
        answers={"languages": ["English"]},
    )
    assert ans["status"] == "ok"

    # 1. Preferences synced completely
    prefs = preferences.load()
    assert prefs["target_titles"] == ["DevOps Engineer"]
    assert prefs["work_mode"] == "Remote"
    assert prefs["min_salary"] == 80000
    assert "Full-time" in prefs["job_types"]
    assert "php" in prefs["excluded_keywords"]
    assert prefs["languages"] == ["English"]

    # 2. Matching and ranking scores updated against the user's preferences
    q_res = v5_tools.jh_query(session_id=sid)
    jobs = q_res["data"]["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "job_remote_devops"
    assert jobs[0]["score"] > 0

    # 3. Tailoring uses user's confirmed target role & preferences instead of old experience title
    srv = mcp_server.create_server(str(isolated_ux_env["ws"]), surface="full")
    out = asyncio.run(srv.call_tool("tailor_resume", {"job_id": "job_remote_devops"}))
    blocks = out[0] if isinstance(out, tuple) else out
    t_res = json.loads(blocks[0].text)
    assert t_res["success"] is True
    tailored = t_res["data"]["tailored_resume"]
    assert "DevOps Engineer" in tailored["summary"]
    assert tailored.get("work_mode_preference") == "Remote"
    assert tailored.get("languages") == ["English"]


def test_team_surface_scan_and_set_preferences_unlock_search_without_jh_begin(isolated_ux_env):
    ws = isolated_ux_env["ws"]
    srv = mcp_server.create_server(str(ws), surface="team")

    def call_tool(name, **kwargs):
        out = asyncio.run(srv.call_tool(name, kwargs))
        blocks = out[0] if isinstance(out, tuple) else out
        return json.loads(blocks[0].text)

    # First run with preferences set via ceo_run setup must not deadlock in search_jobs
    setup_res = call_tool(
        "ceo_run",
        request="set me up",
        hints={"preferences": {"target_countries": ["France"], "work_mode": "Remote", "target_titles": ["Backend Engineer"]}},
    )
    assert setup_res["success"] is True

    with patch("jh.pipeline.search", return_value={"jobs": [], "total": 0, "sources": [], "count": 0, "total_stored": 0, "elapsed_ms": 5, "coverage": {"sources_ran": 1, "sources_with_results": 0}}):
        hunt_res = call_tool("ceo_run", request="find backend engineer jobs in France")
    assert hunt_res["data"]["understood"]["intents"] == ["hunt"]
    assert "Call jh_begin first" not in json.dumps(hunt_res)
