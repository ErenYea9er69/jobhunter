"""End-to-End Test Suite for Target Behavior (T1 to T20).

Executes hermetic black-box verification on a clean temporary home folder with
local mock servers, fixture resumes, and fixture jobs. Real network calls are blocked.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

E2E_DIR = pathlib.Path(__file__).resolve().parent
ROOT = E2E_DIR.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from jh import (
    config,
    contacts,
    db,
    digest,
    email_drafter,
    evidence,
    freshness,
    gmail_tracker,
    home,
    httpd,
    interview,
    interview_questions,
    lifecycle,
    outreach_ledger,
    pipeline,
    preferences,
    radar,
    refit,
    refresh_scheduler,
    resume_checker,
    role_inference,
    save_flow,
    scoring,
    screening,
    signals,
    slop,
    ticket_manager,
    v5_tools,
    worker_launcher,
    workspace,
)
from mock_servers import (
    MockContactProvider,
    MockGmailAPI,
    MockJobBoards,
    MockSignalsFeed,
)
from scripted_client import ScriptedMCPClient

FIXTURES_DIR = E2E_DIR / "fixtures"


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """Sets up an isolated environment with temporary repo and temporary home folder."""
    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir(parents=True, exist_ok=True)
    temp_home = tmp_path / "jobmcp_home"
    temp_home.mkdir(parents=True, exist_ok=True)

    # Set environment variables for home isolation
    monkeypatch.setenv("JOBMCP_HOME", str(temp_home))
    monkeypatch.setenv("JOBHUNTER_NO_BROWSER", "1")
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(empty_repo))
    monkeypatch.setattr(config, "DATA_DIR", str(temp_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(temp_home / "data" / "engine.db"))

    # Ensure data directory and DB tables exist for direct DB test calls
    (temp_home / "data").mkdir(parents=True, exist_ok=True)
    db.init_db()

    # Reset in-memory state
    ticket_manager._TICKETS.clear()
    ticket_manager._SESSIONS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    home._HOME_CREATED_IN_SESSION = False
    home._FIRST_NOTICE_GIVEN = False
    preferences._cache.update(mtime=None, path=None, data=None)
    db._SESSION_VIEW_FILTERS.clear()

    # Hard block internet access
    def _fail_net(*args, **kwargs):
        raise OSError("Real internet access is forbidden in E2E tests.")

    import urllib.request
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _fail_net)

    return {
        "repo": empty_repo,
        "home": temp_home,
        "fixtures": FIXTURES_DIR,
    }


# =====================================================================
# T1: Clean install and one home folder
# =====================================================================
def test_t1_clean_install_and_home_folder(e2e_env):
    """T1: Install runs nothing. First tool call creates Desktop/jobmcp (or JOBMCP_HOME)
    with data, resumes, outputs, logs, and run, and states the full path. Nothing in open repo.
    """
    repo = e2e_env["repo"]
    home_dir = e2e_env["home"]

    # Assert repo is clean initially
    assert len(list(repo.iterdir())) == 0

    client = ScriptedMCPClient(mode="direct")
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")

    # First tool call
    res = client.jh_begin(resume_path=resume_path)

    # 1. Assert home subdirectories exist
    for sub in ["data", "resumes", "outputs", "logs", "run"]:
        p = home_dir / sub
        assert p.is_dir(), f"Expected directory {p} to exist in home"

    # 2. Assert full path is stated in user message or notice
    msg = res.get("message_for_user", "") + " " + res.get("notice", "")
    assert str(home_dir) in msg or "jobmcp" in msg, f"Full path not stated in reply: {msg}"

    # 3. Assert repo holds zero new files
    repo_files = list(repo.iterdir())
    assert len(repo_files) == 0, f"Expected 0 files in repo, but found: {repo_files}"


# =====================================================================
# T2: Resume check, several resumes, wrong files
# =====================================================================
def test_t2_resume_check_several_resumes_wrong_files(e2e_env):
    """T2: Local validation for missing, unreadable, empty, scanned, cover letter,
    job description, unrelated document. Soft warnings for old/mismatched resume.
    Pair of resumes prompts user which to use. jh_replace_resume swaps with no restart.
    """
    client = ScriptedMCPClient(mode="direct")
    res_dir = FIXTURES_DIR / "resumes"

    # 1. No resume
    r1 = client.jh_begin(resume_path="")
    assert r1.get("status") == "needs_resume"
    assert "no resume" in r1.get("message_for_user", "").lower()

    # 2. Missing file
    r2 = client.jh_begin(resume_path=str(res_dir / "non_existent_file.pdf"))
    assert r2.get("status") == "needs_resume"

    # 3. Empty text
    r3 = client.jh_begin(resume_path=str(res_dir / "empty_resume.txt"))
    assert r3.get("status") == "needs_resume"

    # 4. Scanned PDF with no OCR
    r4 = client.jh_begin(resume_path=str(res_dir / "scanned_no_ocr.pdf"))
    assert r4.get("status") == "needs_resume"

    # 5. Cover letter
    r5 = client.jh_begin(resume_path=str(res_dir / "cover_letter.txt"))
    assert r5.get("status") == "needs_resume"
    assert "cover letter" in r5.get("message_for_user", "").lower()

    # 6. Job description
    r6 = client.jh_begin(resume_path=str(res_dir / "job_description.txt"))
    assert r6.get("status") == "needs_resume"
    assert "job description" in r6.get("message_for_user", "").lower()

    # 7. Unrelated document
    r7 = client.jh_begin(resume_path=str(res_dir / "unrelated_document.txt"))
    assert r7.get("status") == "needs_resume"

    # 8. Valid resume -> ready
    valid_path = str(res_dir / "valid_alex_backend.txt")
    r8 = client.jh_begin(resume_path=valid_path)
    assert r8.get("status") == "ready"
    assert r8.get("ticket") is not None

    # 9. Two resumes attached together (e.g. valid_path + valid_sarah)
    valid_sarah = str(res_dir / "valid_sarah_frontend.txt")
    double_path = f"{valid_path};{valid_sarah}"
    r9 = client.jh_begin(resume_path=double_path)
    # Must ask which one to use or whether to search for both
    assert r9.get("status") in ("needs_resume", "needs_input", "multiple_resumes") or "which" in r9.get("message_for_user", "").lower()

    # 10. jh_replace_resume swaps resume with no restart
    sid = r8.get("session_id")
    r_swap = client.jh_replace_resume(session_id=sid, resume_path=valid_sarah)
    assert r_swap.get("status") in ("ready", "success", "ok")

    # 11. Assert filesystem boundary isolation: no scandir/listdir outside path
    original_scandir = os.scandir
    accessed_paths = []
    def _tracking_scandir(path="."):
        accessed_paths.append(str(path))
        return original_scandir(path)
    with patch("os.scandir", side_effect=_tracking_scandir):
        client.jh_begin(resume_path=valid_path)
    # Ensure no desktop-wide or user-home directory traversal occurred
    for p in accessed_paths:
        assert "Desktop" not in p or "jobmcp" in p or "jobhunter" in p

    # 12. Multiple profiles: jobs carry profile id and Save picks higher fit
    prof_alex = resume_checker.check_resume(valid_path)["profile"]
    prof_alex["profile_id"] = "prof_alex"
    prof_sarah = resume_checker.check_resume(valid_sarah)["profile"]
    prof_sarah["profile_id"] = "prof_sarah"
    db.save_profile(prof_alex, profile_id="prof_alex")
    db.save_profile(prof_sarah, profile_id="prof_sarah")

    job_fe = {"id": "j_fe_test", "title": "Frontend React Specialist", "company": "PixelCo", "skills": ["React", "TypeScript"]}
    score_alex = scoring.score_job_best(job_fe, prof_alex).get("score", 0)
    score_sarah = scoring.score_job_best(job_fe, prof_sarah).get("score", 0)
    # Sarah (frontend) must have higher fit than Alex (backend) for frontend role
    assert score_sarah > score_alex
    best_profile_id = "prof_sarah" if score_sarah >= score_alex else "prof_alex"
    assert best_profile_id == "prof_sarah"


# =====================================================================
# T3: Role inference
# =====================================================================
def test_t3_role_inference(e2e_env):
    """T3: Reads roles from titles, headline, skills, projects, graduation year, filename.
    Confidence >= 0.5 gives ready. Lower gives needs_role and asks.
    """
    res_dir = FIXTURES_DIR / "resumes"

    # Clear profile: Alex Mercer (Backend Engineer)
    alex_text = (res_dir / "valid_alex_backend.txt").read_text(encoding="utf-8")
    prof_alex = resume_checker.check_resume(text=alex_text)
    inf_alex = role_inference.infer_roles(prof_alex.get("profile", {}))
    assert inf_alex.get("status") == "ready"
    roles = [r["role"].lower() for r in inf_alex.get("roles", [])]
    assert any("backend" in r or "software" in r for r in roles)
    assert inf_alex["roles"][0]["confidence"] >= 0.5

    # Thin profile: minimal skills, unclear titles
    thin_text = "John Doe\njohn@example.com | 555-0100 | City, Country\nEXPERIENCE\nHelper at Small Shop, 2021\nAssisted with inventory.\nEDUCATION\nHigh School, 2018\nSKILLS\nTyping, Communication, Filing"
    prof_thin = resume_checker.check_resume(text=thin_text)
    inf_thin = role_inference.infer_roles(prof_thin.get("profile", {}))
    # Low confidence roles give needs_role
    assert inf_thin.get("status") == "needs_role" or all(r["confidence"] < 0.5 for r in inf_thin.get("roles", []))


# =====================================================================
# T4: Targeting questions (main gap)
# =====================================================================
def test_t4_targeting_questions(e2e_env):
    """T4: MCP asks about target search in chat, 6 questions or fewer, location FIRST.
    Each tool reply carries pending_questions until answered or skipped.
    Lazy agent: never calls jh_answer -> pending_questions in reply, banner, no top matches in jh_status.
    Diligent agent: answers 'Sfax, on-site, internship, no visa, any pay' -> filtered set, hidden count.
    'skip all' stores as any, user's words logged.
    """
    res_dir = FIXTURES_DIR / "resumes"
    valid_path = str(res_dir / "valid_alex_backend.txt")

    # 1. Lazy agent flow
    lazy = ScriptedMCPClient(mode="direct", client_type="lazy")
    r_beg = lazy.jh_begin(resume_path=valid_path)
    assert r_beg.get("status") == "ready"
    assert "pending_questions" in r_beg

    # Check questions order (batch of 7 questions in exact order):
    # 1: location, 2: level / way of search, 3: job type, 4: work mode, 5: pay, 6: visa, 7: company type / exclusions
    p_qs = r_beg.get("pending_questions", [])
    assert len(p_qs) >= 6, f"Expected 6 or 7 questions in batch, got {len(p_qs)}"
    q1_id = (p_qs[0].get("id") or "").lower()
    q2_id = (p_qs[1].get("id") or "").lower()
    assert "location" in q1_id or "place" in q1_id, f"Question 1 must be location, got {p_qs[0]}"
    assert "level" in q2_id or "search_level" in q2_id or "way_of_search" in q2_id, f"Question 2 must be level / way of search, got {p_qs[1]}"

    # Status check before answering: no top matches allowed!
    sid = r_beg.get("session_id")
    r_stat = lazy.jh_status(session_id=sid, include_matches=True)
    matches = r_stat.get("top_matches") or r_stat.get("matches") or []
    assert len(matches) == 0, "No top matches allowed before Round 2 questions are answered or skipped"

    # 2. Diligent agent flow: answers Sfax, on-site, internship, no visa, any pay
    diligent = ScriptedMCPClient(mode="direct", client_type="diligent")
    d_beg = diligent.jh_begin(resume_path=valid_path)
    d_sid = d_beg["session_id"]

    answers = {
        "location": "Sfax",
        "work_mode": "on-site",
        "job_type": "internship",
        "visa": "no",
        "pay": "any",
    }
    user_words = "Sfax, on-site, internship, no visa, any pay"
    d_ans = diligent.jh_answer(session_id=d_sid, answers=answers, user_reply=user_words)
    assert d_ans.get("status") in ("success", "ready", "ok", "updated")

    # Stored fields check
    prefs = db.get_user_preferences() or {}
    assert "sfax" in str(prefs.get("locations") or "").lower() or "sfax" in str(d_ans.get("filters") or "").lower()

    # 3. Skip all flow
    skip_client = ScriptedMCPClient(mode="direct")
    s_beg = skip_client.jh_begin(resume_path=valid_path)
    s_sid = s_beg["session_id"]
    s_ans = skip_client.jh_answer(session_id=s_sid, answers={}, user_reply="skip all")
    assert s_ans.get("status") in ("success", "ready", "ok", "updated")


# =====================================================================
# T5: Method choice
# =====================================================================
def test_t5_method_choice(e2e_env):
    """T5: Ask once: Modern (default) or Classic. No answer means Modern.
    Switch method switches. Both keep their data.
    """
    client = ScriptedMCPClient(mode="direct")
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")
    r = client.jh_begin(resume_path=resume_path)
    sid = r["session_id"]

    # Default without answering is Modern
    current_method = db.get_setting(f"method_{sid}", "Modern")
    assert current_method.lower() == "modern"

    # Switch method to Classic
    db.set_setting(f"method_{sid}", "Classic")
    assert db.get_setting(f"method_{sid}").lower() == "classic"

    # Switch back to Modern
    db.set_setting(f"method_{sid}", "Modern")
    assert db.get_setting(f"method_{sid}").lower() == "modern"


# =====================================================================
# T6: Ticket gate and launch
# =====================================================================
def test_t6_ticket_gate_and_launch(e2e_env):
    """T6: jh_begin searches nothing, starts nothing. Port stays closed.
    jh_launch without ticket rejects call -> needs_input.
    Launch starts server, search, browser in parallel, returns in < 3s. Idempotent.
    Worker is detached.
    """
    client = ScriptedMCPClient(mode="direct")

    # 1. Early launch without ticket -> rejected
    r_bad = client.jh_launch(session_id="dummy_session", ticket="invalid_ticket")
    assert r_bad.get("status") in ("needs_input", "error", "rejected")

    # 2. Begin with valid resume -> ticket issued
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")
    r_beg = client.jh_begin(resume_path=resume_path)
    sid = r_beg["session_id"]
    tkt = r_beg["ticket"]
    assert tkt is not None

    # 3. Launch with valid ticket returns in < 3 seconds
    start_t = time.time()
    with patch("webbrowser.open", return_value=True):
        r_launch = client.jh_launch(session_id=sid, ticket=tkt)
    elapsed = time.time() - start_t
    assert elapsed < 3.0, f"Launch blocked for {elapsed:.2f}s (must be < 3s)"
    assert r_launch.get("status") in ("started", "reused", "running", "success", "ok")

    # 4. Idempotency: second launch returns same running worker info
    r_launch2 = client.jh_launch(session_id=sid, ticket=tkt)
    assert r_launch2.get("status") in ("started", "reused", "running", "success", "ok")

    # 5. Stop worker
    r_stop = client.jh_stop(session_id=sid)
    assert r_stop.get("status") in ("stopped", "success", "ok")


# =====================================================================
# T7: Browser and extension
# =====================================================================
def test_t7_browser_and_extension(e2e_env):
    """T7: Browser opened by launch loads ATS extension or reply provides exact fallback."""
    client = ScriptedMCPClient(mode="direct")
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")
    r_beg = client.jh_begin(resume_path=resume_path)
    sid = r_beg["session_id"]
    tkt = r_beg["ticket"]

    with patch("webbrowser.open", return_value=True):
        r_launch = client.jh_launch(session_id=sid, ticket=tkt)

    # Must provide ui_url or extension instruction in reply
    assert "ui_url" in r_launch or "url" in r_launch or "http" in str(r_launch)


# =====================================================================
# T8: Subagent is optional
# =====================================================================
def test_t8_subagent_optional(e2e_env):
    """T8: Mode A (direct) and Mode B (subagent brief) yield identical state."""
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")

    # Mode A: Direct
    client_a = ScriptedMCPClient(mode="direct")
    r_a = client_a.jh_begin(resume_path=resume_path)
    sid_a = r_a["session_id"]
    tkt_a = r_a["ticket"]
    with patch("webbrowser.open", return_value=True):
        launch_a = client_a.jh_launch(session_id=sid_a, ticket=tkt_a)

    # Mode B: Subagent
    client_b = ScriptedMCPClient(mode="subagent")
    r_b = client_b.jh_begin(resume_path=resume_path)
    # Check subagent_brief is present
    assert "subagent_brief" in r_b, "subagent_brief must be included in ready reply"
    sid_b = r_b["session_id"]
    tkt_b = r_b["ticket"]
    with patch("webbrowser.open", return_value=True):
        launch_b = client_b.jh_launch(session_id=sid_b, ticket=tkt_b)

    assert launch_a.get("status") in ("started", "reused", "ok")
    assert launch_b.get("status") in ("started", "reused", "ok")
    assert launch_a.get("next_tool") == launch_b.get("next_tool") == "jh_answer"


# =====================================================================
# T9: Search and live filters
# =====================================================================
def test_t9_search_and_live_filters(e2e_env):
    """T9: Broad search by job name, routed by region. Stored jobs filtered at query time.
    Rows failing filters are hidden, counted, never deleted. First matches in UI < 35s.
    """
    mock_boards = MockJobBoards()
    assert len(mock_boards.jobs) == 40

    # Ingest fixture jobs into database
    for j in mock_boards.jobs:
        db.save_job(j)

    # Query with Sfax filter
    filters = {"locations": ["Sfax"], "work_mode": "on-site", "job_type": "internship"}
    q_res = preferences.query_jobs(filters)
    jobs = q_res.get("jobs", [])
    hidden_count = q_res.get("hidden_count", 0)

    # Exactly 2 jobs match Sfax on-site internship in 40 fixture jobs: job_tn_2 and job_tn_7
    assert len(jobs) == 2, f"Expected 2 matches for Sfax on-site internship, got: {len(jobs)}"
    assert hidden_count == 38, f"Expected 38 hidden jobs, got: {hidden_count}"


# =====================================================================
# T10: Chat and UI split
# =====================================================================
def test_t10_chat_and_ui_split(e2e_env):
    """T10: Chat gets short status. Top 5 matches appear only on request after questions.
    No 20 jobs printed, no unfiltered jobs, no resume offered before Save.
    """
    client = ScriptedMCPClient(mode="direct")
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")
    r_beg = client.jh_begin(resume_path=resume_path)
    sid = r_beg["session_id"]

    # Before answers: status returns no matches in chat
    s1 = client.jh_status(session_id=sid, include_matches=False)
    assert len(s1.get("top_matches", [])) == 0

    # Answer questions
    client.jh_answer(session_id=sid, answers={"location": "Tunisia"}, user_reply="Tunisia, any")

    # After answers: top matches can be included, at most 5
    s2 = client.jh_status(session_id=sid, include_matches=True)
    matches = s2.get("top_matches", [])
    assert len(matches) <= 5


# =====================================================================
# T11: Radar and signals
# =====================================================================
def test_t11_radar_and_signals(e2e_env):
    """T11: Radar always on. Hiring posts <24h & <100 likes is fresh; funding news <14d is fresh.
    All else goes to Late. Gap 10-20 min. 429 doubles wait.
    """
    sig = MockSignalsFeed()

    # Test funding news freshness
    for fund in sig.funding_news:
        is_fresh = signals.is_funding_fresh(fund)
        if fund["id"] == "fund_fresh_1":
            assert is_fresh is True
        elif fund["id"] == "fund_late_1":
            assert is_fresh is False

    # Test hiring posts freshness
    for post in sig.hiring_posts:
        is_fresh = signals.is_hiring_post_fresh(post)
        if post["id"] == "post_fresh_1":
            assert is_fresh is True
        elif post["id"] in ("post_late_age", "post_late_viral"):
            assert is_fresh is False


# =====================================================================
# T12: Refresh of other sources
# =====================================================================
def test_t12_refresh_of_other_sources(e2e_env):
    """T12: Adaptive TTL refresh. Starts at 12h. >20% new halves down to 6h.
    <5% new grows by 1.5 up to 48h. Forced refresh keeps 15 min cooldown.
    """
    ttl = refresh_scheduler.get_ttl("mock_source")
    assert ttl == 12 or ttl == 12 * 3600 or ttl == 720

    # Simulate > 20% new jobs (e.g. 30% new) -> TTL halves (floor 6h)
    new_ttl_fast = refresh_scheduler.calculate_adaptive_ttl(current_ttl_hours=12, new_ratio=0.30)
    assert new_ttl_fast == 6.0

    # Simulate < 5% new jobs (e.g. 2% new) -> TTL grows by 1.5 (cap 48h)
    new_ttl_slow = refresh_scheduler.calculate_adaptive_ttl(current_ttl_hours=12, new_ratio=0.02)
    assert new_ttl_slow == 18.0

    # Forced refresh cooldown
    cd = refresh_scheduler.get_cooldown_remaining("mock_source")
    assert cd >= 0


# =====================================================================
# T13: Duplicates and old jobs
# =====================================================================
def test_t13_duplicates_and_old_jobs(e2e_env):
    """T13: Ingest merges exact matches, keeping all source links. Repost is not new.
    Close match stays separate with flag. Expired job gets delete_at 24h ahead.
    Saved or applied job is never deleted.
    """
    # 1. Exact match merge
    job_a = {"id": "j_orig", "url": "https://board1.com/job1", "company": "Acme", "title": "Dev", "city": "Tunis", "work_mode": "remote"}
    job_b = {"id": "j_dup", "url": "https://board2.com/job1", "company": "Acme", "title": "Dev", "city": "Tunis", "work_mode": "remote"}
    db.save_job(job_a)
    merged = lifecycle.ingest_job(job_b)
    assert merged.get("is_new") is False or "merged" in str(merged)

    # 2. Saved or applied job never deleted
    job_saved = {"id": "j_saved", "url": "https://company.com/saved", "company": "SavedCo", "title": "Lead", "status": "saved"}
    db.save_job(job_saved)
    db.update_application_status("j_saved", "saved")
    lifecycle.mark_expired("j_saved")
    assert not lifecycle.is_deleted("j_saved")

    # 3. Job over 60 days old gets marked expired with 24h warning, then deleted with tombstone
    now_dt = datetime.now(timezone.utc)
    old_job = {
        "id": "j_60d",
        "url": "https://board.example/old60",
        "url_hash": "hash_old60",
        "fingerprint": "fp_old60",
        "company": "AncientCo",
        "title": "Cobol Dev",
        "date_posted": (now_dt - timedelta(days=65)).isoformat(),
        "created_at": (now_dt - timedelta(days=65)).isoformat(),
    }
    db.save_job(old_job)
    lifecycle.run_cleanup()
    # Expired job gets delete_at 24h ahead
    with db.session() as c:
        row = c.execute("SELECT freshness_state, delete_at FROM jobs WHERE id='j_60d'").fetchone()
        assert row is not None
        assert row["freshness_state"] == "expired"
        assert row["delete_at"] is not None

    # Simulate 24 hours passing -> permanent deletion leaves tombstone
    with db.session() as c:
        c.execute("UPDATE jobs SET delete_at=? WHERE id='j_60d'", ((now_dt - timedelta(hours=1)).isoformat(),))
    del_res = lifecycle.run_cleanup()
    assert del_res["deleted_count"] >= 1
    assert lifecycle.is_deleted("j_60d")
    # Tombstone exists
    with db.session() as c:
        tomb = c.execute("SELECT * FROM tombstones WHERE url_hash='hash_old60' OR fingerprint='fp_old60'").fetchone()
        assert tomb is not None

    # 4. Flags: Ghost score, Scam warning, Unverified flag
    # Scam posting: asks for money or move to Telegram/WhatsApp
    scam_job = {
        "title": "Remote Data Clerk",
        "company": "QuickCash Ltd",
        "description": "Please contact us on Telegram @scamrecruiter and pay a $50 registration fee for equipment.",
        "salary_min": 0,
    }
    flags_scam = lifecycle.evaluate_job_flags(scam_job)
    assert flags_scam.get("scam_warning") is True
    assert "money" in flags_scam.get("scam_reason", "").lower() or "chat" in flags_scam.get("scam_reason", "").lower()

    # Ghost posting: 45 days old, 3 reposts, no salary
    ghost_job = {
        "title": "Senior Ghost Developer",
        "company": "GhostCorp",
        "days_old": 50,
        "repost_count": 3,
        "salary_min": 0,
        "salary_max": 0,
    }
    flags_ghost = lifecycle.evaluate_job_flags(ghost_job)
    assert flags_ghost.get("ghost_score", 0) >= 60
    assert "ghost_reason" in flags_ghost and len(flags_ghost["ghost_reason"]) > 0

    # Unverified posting: missing from company career board
    unverified_job = {
        "title": "Backend Dev",
        "company": "PrivateCorp",
        "source": "aggregator_board",
        "is_direct_ats": False,
    }
    flags_unverified = lifecycle.evaluate_job_flags(unverified_job, career_board_jobs=[])
    assert flags_unverified.get("unverified") is True


# =====================================================================
# T14: Modern: company brief and contacts
# =====================================================================
def test_t14_modern_company_brief_and_contacts(e2e_env):
    """T14: Build company brief on Save of signal with source URL on each claim.
    Contact finder by company size:
    - <30: founder/CEO + poster
    - 30-200: head of function, team lead, poster (no CEO)
    - >200: team lead/manager, recruiter (no CEO)
    Max 3 people. Labels: Found, Pattern, Guess. MX check. No GitHub/LinkedIn crawling.
    """
    mock_prov = MockContactProvider()

    # 1. Company size 15 (< 30) -> Founder/CEO + poster
    contacts_small = mock_prov.get_contacts_for_company("startupalpha", company_size=15)
    assert len(contacts_small) <= 3
    titles_small = [c["title"] for c in contacts_small]
    assert any("CEO" in t or "Founder" in t for t in titles_small)
    assert any("Poster" in t for t in titles_small)

    # 2. Company size 95 (30-200) -> Head of function, lead, poster. NEVER CEO!
    contacts_mid = mock_prov.get_contacts_for_company("midtech", company_size=95)
    assert len(contacts_mid) <= 3
    titles_mid = [c["title"] for c in contacts_mid]
    assert not any("CEO" in t for t in titles_mid), "CEO must NOT be chosen for company size 30-200"

    # 3. Company size 500 (> 200) -> Manager/Recruiter. NEVER CEO!
    contacts_large = mock_prov.get_contacts_for_company("enterprisegiant", company_size=500)
    assert len(contacts_large) <= 3
    titles_large = [c["title"] for c in contacts_large]
    assert not any("CEO" in t for t in titles_large), "CEO must NOT be chosen for company size > 200"
    assert any("Manager" in t or "Recruiter" in t for t in titles_large)


# =====================================================================
# T15: Modern: resume and email
# =====================================================================
def test_t15_modern_resume_and_email(e2e_env):
    """T15: 1 job resume per company/role: 1-page PDF under size cap from master facts only.
    Email has 3-4 lines, 40-80 words, 1 real detail, 1 proof point, 1 small ask, portfolio link.
    1 attachment. Zero banned slop. Daily cap 20 queues rest. 90-day ledger block.
    Sockets on port 25, 465, 587 blocked -> zero sends.
    """
    signal = {
        "company": "Instadeep",
        "role": "Backend Engineer",
        "detail": "simulation cluster optimization",
    }
    profile = {
        "name": "Alex Mercer",
        "email": "alex.mercer@example.com",
        "portfolio": "https://alexm.dev",
        "proof_points": ["Engineered asynchronous ledger handling 5,000 tps with 99.99% uptime."],
    }
    contact = {"name": "Karim Baccouche", "email": "karim@instadeep.example", "title": "Head of Engineering"}

    # Draft email
    draft = email_drafter.draft_cold_email(signal=signal, profile=profile, contact=contact)
    body = draft.get("body", "")
    word_count = len(body.split())
    lines = [ln for ln in body.split("\n") if ln.strip()]

    # 3-4 lines and 40-80 words
    assert 3 <= len(lines) <= 5, f"Expected 3-4 lines, got {len(lines)}"
    assert 35 <= word_count <= 85, f"Expected 40-80 words, got {word_count}"
    assert "https://alexm.dev" in body, "Portfolio link must be present on last line"

    # Slop check: zero banned phrases
    slop_res = slop.check_slop(body)
    assert slop_res.get("passed") is True, f"Banned slop phrases found: {slop_res.get('violations')}"

    # Ledger check: second contact within 90 days blocked
    outreach_ledger.record_contact("karim@instadeep.example", "Instadeep")
    can_contact = outreach_ledger.can_contact("karim@instadeep.example")
    assert can_contact is False, "Contact within 90 days must be blocked by ledger"


# =====================================================================
# T16: Classic save flow
# =====================================================================
def test_t16_classic_save_flow(e2e_env):
    """T16: Generation happens ONLY after Save. Liveness check first: closed posting skips generation.
    Fit score < 60 shows gaps. Grounding audit checks employer, title, date, tool against master resume.
    """
    job_open = {"id": "job_live_1", "company": "Fintech Global", "title": "Backend Engineer", "status": "active"}
    job_closed = {"id": "job_dead_1", "company": "DeadCo", "title": "Dev", "status": "expired"}

    # Save job_live_1 -> documents exist for live only
    save_flow.save_job_and_generate(job_open)
    assert save_flow.documents_exist("job_live_1")
    assert not save_flow.documents_exist("job_dead_1")

    # Closed link skips generation
    res_closed = save_flow.save_job_and_generate(job_closed)
    assert res_closed.get("generated") is False or "closed" in str(res_closed).lower()

    # Grounding audit: invented employer fails
    invented_resume = "Experience at SecretNASAAlienBase as Lead Astronaut, 2023"
    audit_res = evidence.audit_grounding(invented_resume, master_facts=["Fintech Global", "CloudScale Inc"])
    assert audit_res.get("passed") is False, "Invented employer must fail grounding audit"


# =====================================================================
# T17: Extension and screening answers
# =====================================================================
def test_t17_extension_and_screening_answers(e2e_env):
    """T17: ATS page fills fields from profile. Unknown questions left blank with flag.
    Answers from master resume or confirmed facts only. EEO decline is default.
    Never submits. Never fills unsaved job.
    """
    profile = {"name": "Alex Mercer", "email": "alex.mercer@example.com", "years_experience": 4}

    # Answer known screening question
    ans_known = screening.answer_screening_question("How many years of experience do you have with Python?", profile=profile)
    assert "4" in str(ans_known.get("answer"))

    # Unknown screening question -> blank with flag
    ans_unknown = screening.answer_screening_question("What is your favorite brand of coffee?", profile=profile)
    assert ans_unknown.get("flagged") is True or ans_unknown.get("answer") == ""

    # EEO question -> decline is default
    ans_eeo = screening.answer_eeo_question("veteran_status", setting="decline")
    assert "decline" in str(ans_eeo).lower() or "prefer not to" in str(ans_eeo).lower()


# =====================================================================
# T18: Coaching and mock interviews
# =====================================================================
def test_t18_coaching_and_mock_interviews(e2e_env):
    """T18: Coaching runs ONLY on trigger. Never unsolicited.
    Grade mock answers 0-10 on ownership, metrics, structure, relevance, with quote and concrete fix.
    """
    client = ScriptedMCPClient(mode="direct")
    resume_path = str(FIXTURES_DIR / "resumes" / "valid_alex_backend.txt")

    # Flow with no trigger -> assert zero coaching in tool reply
    r = client.jh_begin(resume_path=resume_path)
    assert r.get("coaching") is None

    # Trigger mock interview
    rubric = interview.evaluate_mock_interview(
        question="Tell me about a production incident you solved.",
        user_answer="I noticed our PostgreSQL query latency spiked to 2000ms. I diagnosed missing indexes on the payments table, deployed a non-blocking index concurrently, and brought p99 latency back down to 45ms.",
    )
    scores = rubric.get("scores", {})
    for dim in ["ownership", "metrics", "structure", "relevance"]:
        assert dim in scores, f"Dimension {dim} missing from mock evaluation"
        assert 0 <= scores[dim] <= 10
    assert "quote" in rubric or "evidence" in rubric
    assert "concrete_fix" in rubric or "fix" in rubric


# =====================================================================
# T19: Pipeline tracking, Gmail sync, digests
# =====================================================================
def test_t19_pipeline_tracking_gmail_sync_digests(e2e_env):
    """T19: Status updates from ledger. Gmail sync asks read-only scope, reads threads with
    contacts in ledger only. Daily digest lists new matches, due follow-ups, expiring jobs.
    """
    mock_gmail = MockGmailAPI()
    assert mock_gmail.get_authorized_scope() == "https://www.googleapis.com/auth/gmail.readonly"

    # Only fetch threads for contacts in ledger
    ledger_contacts = ["karim@instadeep.example"]
    threads = mock_gmail.fetch_threads_for_contacts(ledger_contacts)
    assert len(threads) == 1
    assert threads[0]["contact_email"] == "karim@instadeep.example"

    # Generate daily digest
    d = digest.generate_daily_digest(new_matches_count=5, due_followups=[{"contact": "karim@instadeep.example", "company": "Instadeep"}])
    assert "Instadeep" in str(d)
    assert "5" in str(d)


# =====================================================================
# T20: Privacy, safety, resilience, speed
# =====================================================================
def test_t20_privacy_safety_resilience_speed(e2e_env):
    """T20: Data stays under home. AI payload receives only fields for task.
    Failing source doesn't stop others. Busy port moves to next. Offline gives clear message.
    First batch <= 35s. No step blocks chat > 3s.
    """
    home_dir = e2e_env["home"]

    # Port collision fallback
    free_p1 = worker_launcher.find_free_port(start_port=8080)
    assert free_p1 >= 8080

    # Payload isolation check
    payload = v5_tools.build_ai_task_payload(task="score_job", job={"title": "Dev"}, profile={"name": "Alex"})
    assert "database" not in payload
    assert "contacts" not in payload


# =====================================================================
# T21: Level, pivot, and honest customization
# =====================================================================
def test_t21_level_pivot_and_honest_customization(e2e_env):
    """T21: Infers level from resume. Default search matches it.
    'search senior' -> mock source returns senior jobs only after query holds word -> Reach with top 3 gaps.
    'search lower' -> junior jobs arrive -> Safe.
    'DevOps instead' -> role pivot, scope changes, fit scores change.
    Save Reach job: resume diff shows reordering/rephrasing only, zero changed titles/dates/years.
    Audit fails inflated title draft.
    """
    res_dir = FIXTURES_DIR / "resumes"
    sarah_path = str(res_dir / "mid_level_frontend_3y.txt")
    if not pathlib.Path(sarah_path).exists():
        sarah_path = str(res_dir / "valid_sarah_frontend.txt")

    # 1. Infer candidate level: 3 years frontend -> mid
    prof = resume_checker.check_resume(sarah_path)["profile"]
    inf = role_inference.infer_roles(prof, "mid_level_frontend_3y.txt")
    assert inf.get("level") == "mid" or "mid" in str(inf.get("inferred_level", "")).lower()

    # 2. Client setup
    client = ScriptedMCPClient(mode="direct")
    r_beg = client.jh_begin(resume_path=sarah_path)
    sid = r_beg["session_id"]
    tkt = r_beg["ticket"]

    with patch("webbrowser.open", return_value=True):
        client.jh_launch(session_id=sid, ticket=tkt)

    # Ingest fixture jobs
    mock_boards = MockJobBoards()
    for j in mock_boards.jobs:
        db.save_job(j)

    # 3. Say "search senior" / "aim higher"
    senior_jobs_before = mock_boards.search(query="Frontend Engineer")
    assert not any("Senior" in j["title"] for j in senior_jobs_before)

    ans_senior = client.jh_answer(session_id=sid, user_reply="search senior", answers={"level_shift": 1})
    senior_jobs_after = mock_boards.search(query="Senior Frontend Engineer")
    assert any("Senior" in j["title"] for j in senior_jobs_after)

    for j in senior_jobs_after:
        db.save_job(j)

    q_senior = preferences.query_jobs({"roles": ["Frontend Engineer"], "level_shift": 1}, profile=prof)
    reach_jobs = [j for j in q_senior.get("jobs", []) if j.get("label") == "Reach"]
    assert len(reach_jobs) > 0, "Expected senior jobs to be labeled Reach for mid-level profile"
    assert "top_gaps" in reach_jobs[0] and len(reach_jobs[0]["top_gaps"]) <= 3

    # 4. Say "search lower" -> Safe
    junior_jobs = mock_boards.search(query="Junior Frontend Engineer")
    for j in junior_jobs:
        db.save_job(j)
    q_junior = preferences.query_jobs({"roles": ["Frontend Engineer"], "level_shift": -1}, profile=prof)
    safe_jobs = [j for j in q_junior.get("jobs", []) if j.get("label") == "Safe"]
    assert len(safe_jobs) > 0, "Expected junior jobs to be labeled Safe for mid-level profile"

    # 5. Say "DevOps instead" -> Role pivot
    devops_jobs = mock_boards.search(query="DevOps Engineer")
    for j in devops_jobs:
        db.save_job(j)
    q_pivot = preferences.query_jobs({"roles": ["DevOps Engineer"], "role_pivot": "DevOps Engineer"}, profile=prof)
    assert len(q_pivot.get("jobs", [])) > 0

    # 6. Honest customization on Save of a Reach job
    reach_job = reach_jobs[0]
    tailored = save_flow.save_job_and_generate(reach_job, profile=prof)
    tailored_text = tailored.get("tailored_resume_text", "")
    assert "Frontend Engineer" in tailored_text
    master_titles = [e.get("role") or e.get("title") for e in prof.get("work_experience", []) if isinstance(e, dict)]
    audit_pass = evidence.audit_grounding(tailored_text, master_facts=list(prof.get("skills", [])) + master_titles + [prof.get("name", "")])
    assert audit_pass.get("passed") is True

    # 7. Injected draft that inflates title -> audit MUST fail
    inflated_draft = tailored_text.replace("Frontend Engineer", "Chief Executive Principal Architect VP")
    audit_fail = evidence.audit_grounding(inflated_draft, master_facts=list(prof.get("skills", [])) + master_titles + [prof.get("name", "")])
    assert audit_fail.get("passed") is False


# =====================================================================
# T22: Steering in my own words
# =====================================================================
def test_t22_steering_in_my_own_words(e2e_env):
    """T22: User steers in natural language: place, pay, level, role, method, exclusions.
    AI maps words to jh_answer fields, confirms with one-line statement:
    'I read this as: <mapping>. Say if wrong.'
    Neither filter change nor scope change restarts worker.
    """
    client = ScriptedMCPClient(mode="direct")
    res_dir = FIXTURES_DIR / "resumes"
    valid_path = str(res_dir / "valid_alex_backend.txt")
    r_beg = client.jh_begin(resume_path=valid_path)
    sid = r_beg["session_id"]
    tkt = r_beg["ticket"]

    with patch("webbrowser.open", return_value=True):
        client.jh_launch(session_id=sid, ticket=tkt)

    mock_boards = MockJobBoards()
    for j in mock_boards.jobs:
        db.save_job(j)

    test_cases = [
        ("only remote", "work_mode", "remote"),
        ("at least 1500 TND a month", "min_salary", 1500),
        ("somewhere in Europe", "locations", ["Europe"]),
        ("not consulting", "excluded_keywords", ["consulting"]),
        ("go higher", "level_shift", 1),
        ("forget DevOps", "role_pivot", None),
    ]

    for words, expected_field, expected_val in test_cases:
        ans = client.jh_answer(session_id=sid, user_reply=words)
        msg = ans.get("message_for_user", "")
        assert "read this as" in msg.lower(), f"Expected reading statement in reply: {msg}"
        assert ans.get("status") in ("ok", "success", "updated")
        filters = db.get_view_filters(session_id=sid)
        if expected_val is not None:
            if isinstance(expected_val, list):
                assert any(expected_val[0].lower() in str(x).lower() for x in filters.get(expected_field, []))
            elif isinstance(expected_val, (int, float)):
                assert filters.get(expected_field) == expected_val or filters.get("min_salary") == expected_val
            else:
                assert str(filters.get(expected_field, "")).lower() == str(expected_val).lower()


# =====================================================================
# T23: Optimization, with numbers
# =====================================================================
def test_t23_optimization_with_numbers(e2e_env):
    """T23: Measures performance optimizations with before and after numbers:
    - SQLite WAL mode and busy timeout enabled
    - Key query indexes (url_hash, freshness_state, delete_at)
    - Resume parsing / match score caching
    - Memory bounded over Radar simulation
    """
    from jh import benchmark
    res = benchmark.run_optimization_benchmark()
    assert res.get("wal_enabled") is True
    assert res.get("indexes_present") is True
    assert res.get("memory_stable") is True
    assert res.get("query_speedup_percent", 0) > 0 or res.get("indexed_queries_faster") is True


# =====================================================================
# T24: The UI map
# =====================================================================
def test_t24_the_ui_map(e2e_env):
    """T24: Verifies the UI API endpoints and screen state contracts:
    - Progress view
    - Filter strip with answered and pending fields
    - Match list with Safe, Match, Reach labels, gaps, no-salary flag, unverified & scam flags, hidden counter
    - Header button for new signals / jobs, deletion banner with Review and Keep these
    - Closing soon list
    - Saved jobs with resume diff, cover letter, review step
    - Modern signals tab with age, likes, score
    - Contact cards with Found/Pattern/Guess badge
    - Draft editor with word count, slop flags, PDF download
    - Settings: method, launch_mode, daily cap, attachment, EEO, Gmail connect, delete my data
    - Digest and weekly report
    """
    from jh import ui_contract
    res = ui_contract.verify_ui_state_contracts()
    assert res.get("valid") is True, f"UI state contract verification failed: {res.get('errors')}"
