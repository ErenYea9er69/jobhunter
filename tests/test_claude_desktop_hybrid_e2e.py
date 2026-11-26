"""End-to-end verification of the v2.0.0 Claude Desktop Hybrid MCP workflow."""
from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import mcp_server
from jh import config, db, lifecycle, pipeline, radar, ticket_manager, v5_tools, worker_launcher
from conftest import SAMPLE_RESUME


@pytest.fixture(autouse=True)
def isolated_hybrid_desktop_env(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    resumes_dir = ws / "resumes"
    resumes_dir.mkdir(exist_ok=True)
    (resumes_dir / "ahmed.txt").write_text(SAMPLE_RESUME, encoding="utf-8")

    home_dir = tmp_path / "jobmcp_home"
    home_dir.mkdir(parents=True, exist_ok=True)
    data_dir = home_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("JOBMCP_HOME", str(home_dir))
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(config, "DB_PATH", str(data_dir / "state"))

    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    monkeypatch.setattr(radar, "start_radar_worker", lambda *a, **kw: None)
    monkeypatch.setattr(pipeline, "search", lambda *a, **kw: {"jobs": [], "total": 0, "statuses": []})
    return {"ws": ws, "home": home_dir, "data": data_dir}


def test_claude_desktop_hybrid_workflow_end_to_end(isolated_hybrid_desktop_env):
    ws = isolated_hybrid_desktop_env["ws"]
    home_dir = isolated_hybrid_desktop_env["home"]
    sid = "claude_hybrid_e2e"

    # 1. Start session cleanly: Hybrid-only (no Method choice prompt, no location guessing)
    b = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id=sid)
    assert b["status"] in ("needs_target", "needs_role")
    assert "method" not in str(b.get("options", {}).get("questions", [])).lower()

    # 2. Confirm target place directly without artificial reply timers -> ready ticket
    c = v5_tools.jh_confirm(session_id=sid, user_reply="Remote Europe")
    assert c["status"] == "ready"
    tkt = c["ticket"]

    # 3. Launch headless Hybrid discovery (no HTTP server, no browser, no .db file)
    l_res = v5_tools.jh_launch(session_id=sid, ticket=tkt)
    assert l_res["status"] == "ok"
    assert l_res["data"]["method"] == "hybrid"
    assert "ui_url" not in l_res

    # Seed relevant recent vs older/mismatched jobs to test fit + recency ranking and filtering
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_iso = (now - datetime.timedelta(hours=2)).isoformat()
    older_iso = (now - datetime.timedelta(days=12)).isoformat()
    db.store_jobs([
        {
            "id": "job_recent_strong",
            "title": "Senior Backend Engineer",
            "company": "NordicPay",
            "location": "Remote, Europe",
            "country": "France",
            "work_mode": "Remote",
            "job_type": "full-time",
            "url": "https://nordicpay.example/jobs/backend",
            "description": "Build Python, FastAPI, PostgreSQL, Redis and Docker microservices.",
            "posted_at": recent_iso,
            "score": 92,
        },
        {
            "id": "job_older_medium",
            "title": "Backend Engineer",
            "company": "LegacySoft",
            "location": "Remote, Europe",
            "country": "Germany",
            "work_mode": "Remote",
            "job_type": "full-time",
            "url": "https://legacysoft.example/jobs/backend",
            "description": "Maintain Python APIs and PostgreSQL.",
            "posted_at": older_iso,
            "score": 76,
        },
        {
            "id": "job_excluded_onsite",
            "title": "Onsite PHP Developer",
            "company": "LocalShop",
            "location": "Madrid, Spain",
            "country": "Spain",
            "work_mode": "Onsite",
            "job_type": "full-time",
            "url": "https://localshop.example/jobs/php",
            "description": "Onsite PHP role.",
            "posted_at": recent_iso,
            "score": 40,
        },
    ], query="Backend Engineer")

    # 4. User refines filters -> returns Reviewer-verified top matches ranked by fit + recency directly in chat
    a_res = v5_tools.jh_answer(session_id=sid, user_reply="remote, full-time")
    assert a_res["status"] == "ok"
    q_res = v5_tools.jh_query(session_id=sid)
    assert q_res["status"] == "ok"
    matches = q_res["data"].get("jobs") or q_res["data"].get("top_matches") or q_res["data"].get("matches") or []
    assert isinstance(matches, list) and len(matches) >= 2
    assert matches[0]["title"] == "Senior Backend Engineer"
    assert matches[0]["company"] == "NordicPay"

    # 5. User selects specific match -> prepare grounded tailored resume, cover letter, 1-page PDF & contacts/outreach draft
    srv = mcp_server.create_server(str(ws), surface="full")

    def call_tool(name, **kwargs):
        out = asyncio.run(srv.call_tool(name, kwargs))
        blocks = out[0] if isinstance(out, tuple) else out
        return json.loads(blocks[0].text)

    tailored = call_tool("tailor_resume", job_id="job_recent_strong")
    assert tailored["success"] is True
    assert tailored["data"]["grounding"]["supported"] >= 5
    tailored_blob = json.dumps(tailored["data"]["tailored_resume"])
    assert "Vermeg" in tailored_blob and "Sofrecom" in tailored_blob

    cover = call_tool("cover_letter", job_id="job_recent_strong")
    assert cover["success"] is True
    assert "NordicPay" in cover["data"]["letter"]

    db.ingest_signal({
        "id": "sig_nordic",
        "type": "hiring_post",
        "company": "NordicPay",
        "company_domain": "nordicpay.example",
        "author_name": "Astrid Lindqvist",
        "author_url": "https://linkedin.com/in/astrid-lindqvist",
        "role_guess": "Senior Backend Engineer",
        "text": "Hiring Senior Backend Engineer for Python and FastAPI microservices.",
        "posted_at": recent_iso,
        "status": "fresh",
    })
    pdf_res = v5_tools.jh_build_resume(company="NordicPay", role="Senior Backend Engineer", signal_id="sig_nordic")
    assert pdf_res["status"] == "ok"
    pdf_path = pdf_res["data"].get("resume_path") or pdf_res["data"].get("pdf_path") or pdf_res["data"].get("path")
    assert pdf_path and Path(pdf_path).is_file()

    with patch("jh.email_finder.query_mx_records", return_value={"has_mx": True, "provider": "Google"}):
        contacts_res = v5_tools.jh_find_contacts("sig_nordic", target_role="Senior Backend Engineer")
    assert contacts_res["status"] == "ok"
    contacts_list = contacts_res["data"].get("contacts", [])
    assert len(contacts_list) >= 1

    draft = v5_tools.jh_draft_email(
        contact_id=contacts_list[0]["id"],
        signal_id="sig_nordic",
        resume_path=str(pdf_path),
    )
    assert draft["status"] == "ok"
    assert draft["data"].get("auto_sent") is not True

    # 6. Confirm zero .db / SQLite files anywhere in workspace or home
    db_files = list(home_dir.rglob("*.db*")) + list(ws.rglob("*.db*"))
    assert db_files == []
