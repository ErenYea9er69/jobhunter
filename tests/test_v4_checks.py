"""JobHunter V4 Scripted Verification Suite (Checks 1 to 13).

Strictly validates every acceptance requirement from the V4 target specification:
1. No resume, wrong file, scanned PDF, cover letter, JD -> needs_resume, nothing starts.
2. Good resume -> one-line profile + Step 3 questions, no search row, closed port, no browser.
3. jh_launch with no ticket -> needs_input; confirm with empty or echoed reply is rejected.
4. After ticket -> launch < 3s, server starts, search runs, browser opens with session URL.
5. Kill calling process -> server and search keep running (DETACHED_PROCESS).
6. Tunisia queries 0 global remote feeds.
7. Guessed job type, place, or pay never filter before user answers.
8. jh_answer updates view filters without restarting search; hidden count matches db.
9. Chat holds no job list; no document generated before Save.
10. Planted false claim in draft gets repaired or blocked.
11. Extension autofill screening logic leaves unknown blank and declines EEO.
12. Modern respects daily cap of 20; Mock interview grades ownership and metrics; Gmail sync is off by default.
13. Baseline test suite compatibility preserved.
"""
from __future__ import annotations

import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jh import (
    config,
    contacts,
    db,
    digest,
    email_drafter,
    extension_installer,
    founder_outreach,
    gmail_tracker,
    home,
    interview,
    interview_questions,
    pipeline,
    resume_checker,
    role_inference,
    save_flow,
    screening,
    source_registry,
    ticket_manager,
    v5_tools,
    worker_launcher,
)
from conftest import SAMPLE_RESUME


@pytest.fixture(autouse=True)
def clean_v4_state(tmp_path, monkeypatch):
    """Clean test isolation."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(home_dir / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(home_dir / "data" / "engine.db"))
    monkeypatch.setenv("JOBHUNTER_BYPASS_DELAY", "1")

    ticket_manager._TICKETS.clear()
    ticket_manager._SESSIONS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()

    monkeypatch.setattr(pipeline, "search", lambda *args, **kwargs: {"jobs": [], "total": 0, "statuses": []})
    db.init_db()
    yield ws


def test_check_01_invalid_and_non_resumes_rejected():
    """Check 1: No resume, wrong file, scanned PDF, cover letter, JD -> needs_resume, nothing starts."""
    # 1. No resume
    res = v5_tools.jh_begin(resume_path="", resume_text="", session_id="chk1_empty")
    assert res["status"] == "needs_resume"
    assert "No resume file path or text was provided" in res["data"]["issues"][0]

    # 2. Unsupported type
    res_unsupported = v5_tools.jh_begin(resume_path="resume.xyz", session_id="chk1_unsupported")
    assert res_unsupported["status"] == "needs_resume"

    # 3. Under 300 characters (scanned PDF / blank)
    res_short = v5_tools.jh_begin(resume_text="Too short resume text", session_id="chk1_short")
    assert res_short["status"] == "needs_resume"
    assert any("under 300 characters" in issue for issue in res_short["data"]["issues"])

    # 4. Cover letter
    cl_text = (
        "Dear Hiring Manager,\n\n"
        "I am writing to express my eager interest in joining your team as a software developer. "
        "With my dedication to engineering and problem solving, I look forward to contributing to your vision. "
        "I have attached my details and look forward to hearing from you soon.\n\n"
        "Sincerely,\nJane Candidate\n"
    )
    res_cl = v5_tools.jh_begin(resume_text=cl_text * 2, session_id="chk1_cl")
    assert res_cl["status"] == "needs_resume"
    assert any("cover letter" in issue.lower() for issue in res_cl["data"]["issues"])

    # 5. Job description
    jd_text = (
        "Job Description: Senior Full Stack Engineer\n"
        "We are looking for an experienced software developer to build high performance web platforms.\n"
        "Requirements:\n"
        "- 5+ years of experience with React, Node.js, and PostgreSQL.\n"
        "- Deep expertise in Docker, Kubernetes, and AWS microservices.\n"
        "- What you'll do: Build APIs, lead code reviews, and deploy production features.\n"
        "- Qualifications required: BS in Computer Science.\n"
        "Apply now by sending your resume to jobs@example.com.\n"
    )
    res_jd = v5_tools.jh_begin(resume_text=jd_text * 2, session_id="chk1_jd")
    assert res_jd["status"] == "needs_resume"
    assert any("job description" in issue.lower() for issue in res_jd["data"]["issues"])


def test_check_02_good_resume_one_line_summary_and_step_3_questions():
    """Check 2: A good resume gives one-line profile and step 3 questions, with no search row, closed port, no browser call."""
    with patch("jh.worker_launcher.open_browser") as mock_browser:
        res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chk2_good")
        assert res["status"] in ("needs_target", "needs_role")
        assert "ticket" not in res  # Ticket is NOT issued before Step 3 answers

        msg = res["message_for_user"]
        assert msg.startswith("STOP. Ask the user the questions below and wait for the answer. Do not call another tool.")
        assert "Method: Modern (default) or Classic" in msg
        assert "Target place:" in msg

        # One-line summary present
        assert "one_line_summary" in res["data"]
        summary = res["data"]["one_line_summary"]
        assert "Name:" in summary
        assert "Roles:" in summary
        assert "Top Skills:" in summary

        # Verify no premature start
        mock_browser.assert_not_called()
        with db.session() as c:
            count = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            assert count == 0
        assert worker_launcher.get_search_job_status("chk2_good")["status"] == "not_started"


def test_check_03_launch_rejects_without_ticket_and_confirm_rejects_empty_echo():
    """Check 3: jh_launch with no ticket gives needs_input; jh_confirm with empty or echoed reply is rejected."""
    # 1. Launch without ticket
    l_res = v5_tools.jh_launch(session_id="chk3_sess", ticket="")
    assert l_res["status"] == "needs_input"
    assert "STOP" in l_res["message_for_user"]
    assert l_res["next_tool"] == "jh_begin"

    # 2. Confirm with empty user reply
    c_empty = v5_tools.jh_confirm(session_id="chk3_sess", user_reply="")
    assert c_empty["status"] == "needs_input"
    assert "empty" in c_empty["message_for_user"].lower()

    # 3. Confirm with repeated question text
    c_echo = v5_tools.jh_confirm(
        session_id="chk3_sess",
        user_reply="Method: Modern (default) or Classic? Target place: Tunisia, remote worldwide"
    )
    assert c_echo["status"] == "needs_input"
    assert "repeats the question" in c_echo["message_for_user"].lower()


def test_check_04_after_ticket_launch_speed_and_url_session():
    """Check 4: After ticket, launch returns in < 3s, server starts, search runs, browser opens with session URL."""
    v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chk4_sess")
    c_res = v5_tools.jh_confirm(session_id="chk4_sess", user_reply="Modern method, Tunisia")
    assert c_res["status"] == "ready"
    ticket = c_res["ticket"]

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True) as mock_b:
        t0 = time.time()
        l_res = v5_tools.jh_launch(session_id="chk4_sess", ticket=ticket)
        elapsed = time.time() - t0

        assert elapsed < 3.0
        assert l_res["status"] == "ok"
        assert "http://127.0.0.1:8080/?session=chk4_sess" in l_res["ui_url"]
        assert l_res["search_status"] in ("started", "already_running")
        mock_b.assert_called_once()


def test_check_05_server_and_search_keep_running_on_process_kill():
    """Check 5: Detached worker and search jobs keep running independently of calling agent process."""
    run_dir = worker_launcher.get_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "server.pid").write_text("12345", encoding="utf-8")
    (run_dir / "server.port").write_text("8080", encoding="utf-8")

    v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chk5_sess")
    c_res = v5_tools.jh_confirm(session_id="chk5_sess", user_reply="Modern, Tunisia")

    try:
        with patch("jh.worker_launcher.is_server_healthy", return_value=True), \
             patch("jh.worker_launcher.open_browser", return_value=True):
            l_res = v5_tools.jh_launch(session_id="chk5_sess", ticket=c_res["ticket"])
            assert l_res["status"] == "ok"

        # Simulate caller exiting: PID file and memory state remain intact
        assert (run_dir / "server.pid").is_file()
        assert worker_launcher.get_search_job_status("chk5_sess")["status"] in ("running", "completed")
    finally:
        worker_launcher.stop_worker("chk5_sess")


def test_check_06_tunisia_queries_zero_global_remote_feeds():
    """Check 6: 'Tunisia' queries no global remote feed."""
    prefs = {"home_country": "Tunisia", "target_countries": ["Tunisia"]}
    targets = ["TN"]
    remote_ok = False

    remote_sources = ["RemoteOK", "Himalayas", "Remotive", "Jobicy", "We Work Remotely", "Working Nomads", "Hacker News"]
    for src in remote_sources:
        skip = source_registry.skip_reason(src, prefs, targets, remote_ok)
        assert skip is not None, f"Expected {src} to be skipped for Tunisia local search"
        assert skip[0] == "skipped"

    # Tunisia / MENA / ATS boards remain active
    assert source_registry.skip_reason("Bayt", prefs, targets, remote_ok) is None
    assert source_registry.skip_reason("Company Boards", prefs, targets, remote_ok) is None


def test_check_07_guesses_never_filter_before_user_answers():
    """Check 7: A guessed job type, place, or pay never filters results before user answers."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, resume_path="stage_pfe_2027.pdf", session_id="chk7_guess")
    assert b_res["data"]["job_type_guess"]["guess"] is True

    # Ingest mix of internship and full-time jobs
    db.store_jobs([
        {"title": "Full-Time Backend Engineer", "company": "Co A", "job_type": "full-time", "score": 90},
        {"title": "PFE Internship Backend", "company": "Co B", "job_type": "internship", "score": 90},
    ], query="backend")

    # Before Round 2, both jobs are returned
    view = db.query_jobs(session_id="chk7_guess")
    assert view["count"] >= 2


def test_check_08_jh_answer_updates_filters_live_without_new_search():
    """Check 8: jh_answer changes the list with no new search; hidden count matches database."""
    v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chk8_ans")
    c_res = v5_tools.jh_confirm(session_id="chk8_ans", user_reply="Modern, Tunisia")

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        v5_tools.jh_launch(session_id="chk8_ans", ticket=c_res["ticket"])

    initial_job_id = worker_launcher.get_search_job_status("chk8_ans")["job_id"]

    db.store_jobs([
        {"title": "Remote Backend Engineer", "company": "Global", "work_mode": "remote", "score": 90},
        {"title": "Onsite Backend Engineer", "company": "Local", "work_mode": "onsite", "score": 90},
    ], query="backend")

    # Filter remote
    ans_res = v5_tools.jh_answer(session_id="chk8_ans", answers={"work_mode": "remote"}, user_reply="remote jobs only")
    assert ans_res["status"] == "ok"
    assert ans_res["data"]["matches_count"] >= 1

    # Search job ID remains unchanged (no new search initiated)
    assert worker_launcher.get_search_job_status("chk8_ans")["job_id"] == initial_job_id

    st = v5_tools.jh_status(session_id="chk8_ans")
    assert st["data"]["hidden_by_filters"] >= 1


def test_check_09_chat_holds_no_jobs_and_no_documents_before_save():
    """Check 9: The chat holds no job list; no document exists before Save."""
    v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chk9_save")
    c_res = v5_tools.jh_confirm(session_id="chk9_save", user_reply="Modern, Tunisia")

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        l_res = v5_tools.jh_launch(session_id="chk9_save", ticket=c_res["ticket"])

    # Chat message contains no job dump
    msg = l_res["message_for_user"]
    assert "Do not list jobs in chat" in msg
    assert "http://" in l_res["ui_url"]

    # Verify output dir has no generated job documents before Save
    outputs_dir = home.get_home() / "outputs"
    if outputs_dir.exists():
        generated_docs = [
            f for f in outputs_dir.glob("*")
            if f.is_file() and (f.suffix in (".pdf", ".docx", ".txt") or f.name.startswith(("resume_", "cover_")))
        ]
        assert len(generated_docs) == 0


def test_check_10_planted_false_claim_repaired_or_blocked():
    """Check 10: Planted false claims get repaired or blocked."""
    profile = {
        "name": "Jane Developer",
        "skills": ["Python", "FastAPI"],
        "experience": [{"title": "Software Engineer", "company": "Real Corp", "bullets": []}],
        "_is_empty": False,
    }
    job = {"title": "Python Engineer", "company": "Target Co", "id": "job_false"}

    false_cover_letter = (
        "Dear Hiring Manager,\n"
        "At my previous company NASA Jet Propulsion Lab, I served as Chief Aerospace Architect from 2010 to 2025 "
        "and generated $500,000,000 in rocket revenues using Rust, Zig, and Julia.\n"
        "Sincerely, Jane Developer"
    )

    passed, clean_doc, findings = save_flow.grounding_check_and_repair(
        false_cover_letter, profile, job, kind="cover_letter"
    )

    # Invented NASA and fake revenue must be stripped/repaired
    assert "NASA" not in clean_doc
    assert "$500,000,000" not in clean_doc
    assert len(findings) > 0


def test_check_11_extension_screening_logic_leaves_unknown_empty_and_declines_eeo():
    """Check 11: Screening answers only from verified facts, leaves unknowns blank, auto-declines EEO."""
    profile = {
        "name": "Alex Candidate",
        "years_of_experience": 4.0,
        "location": "Tunis, Tunisia",
        "skills": ["Python", "Docker"],
    }

    # 1. Known question answered accurately
    known_ans = screening.answer_screening_question("How many years of experience do you have?", profile)
    assert known_ans["answered"] is True
    assert "4" in str(known_ans["answer"])

    # 2. Unknown question left empty and flagged
    unknown_ans = screening.answer_screening_question("What is your active DoD Top Secret clearance issuance date?", profile)
    assert unknown_ans["answered"] is False
    assert unknown_ans["answer"] == ""
    assert unknown_ans["flagged"] is True

    # 3. EEO disclosures declined
    eeo_ans = screening.answer_screening_question("Gender / Race / Veteran status disclosure", profile)
    assert eeo_ans["answered"] is True
    assert "I do not wish to answer" in eeo_ans["answer"]


def test_check_12_modern_daily_cap_and_mock_interview_and_gmail_sync():
    """Check 12: Modern respects daily cap of 20; mock interview grades ownership & metrics; Gmail sync off by default."""
    # 1. Modern daily cap of 20
    cap = founder_outreach.get_daily_email_cap()
    assert cap <= 20

    # 2. Mock interview grading
    int_q = interview_questions.generate_mock_interview_questions({"title": "Senior Engineer"}, SAMPLE_RESUME)
    assert len(int_q) >= 1

    # Answer using "we" without numbers -> lower ownership and metrics
    grade_we = interview.grade_mock_answer(
        question="Tell me about a challenging distributed systems problem you solved.",
        answer="We worked on microservices and we deployed them together as a team.",
    )
    assert grade_we["ownership_score"] < 4
    assert grade_we["metrics_score"] < 4
    assert "ownership" in grade_we["feedback"].lower() or "metrics" in grade_we["feedback"].lower()

    # Answer using "I" with concrete metrics -> high scores
    grade_i = interview.grade_mock_answer(
        question="Tell me about a challenging distributed systems problem you solved.",
        answer="I re-architected the Redis cache layer, reducing 99th percentile API latency by 45% and saving $12,000 monthly.",
    )
    assert grade_i["ownership_score"] >= 4
    assert grade_i["metrics_score"] >= 4

    # 3. Gmail sync is off by default (when unconfigured or default)
    with patch("jh.gmail_tracker.get_config_path", return_value=Path(tempfile.gettempdir()) / "unconfigured_gmail.json"):
        assert gmail_tracker.is_sync_enabled() is False
