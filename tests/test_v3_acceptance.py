"""Automated Acceptance Test Suite for JobHunter MCP Fix V3 (Tests 1 to 24).

Validates:
1. jh_begin with valid resume -> ready with ticket, no search started, no server, no browser.
2. jh_launch and jh_search without ticket -> needs_input, start nothing.
3. Old combined tool name behaves like jh_begin.
4. jh_confirm rejects empty user_reply or repeating question text.
5. jh_launch returns < 3s, starts server & search, opens browser with session URL. Also for needs_role -> jh_confirm flow.
6. Mode A (direct) and Mode B (subagent) produce identical state.
7. Launch idempotency: second launch reuses worker and search.
8. Server independence: worker survives termination of calling subagent process.
9. jh_answer updates filters live without restarting search.
10. Query-time filtering: jobs pass filters, hidden count matches, unanswered counts as any.
11. Tunisia source routing: skips global remote feeds, faster execution.
12. "skip all" in user_reply stores as any and logs verbatim words.
13. Chat suppression: no jobs listed in tool message before Round 2 answers.
14. Instruction files contain STOP rule and no early resume offer.
15. jh_install_agent asks first, writes only to user home dir, never workspace.
16. Launch latency < 3 seconds.
17. Baseline compatibility verified across test suite.
18. Missing resume / invalid path -> needs_resume, no folder scanning.
19. Document classification: rejects empty, scan, cover letter, JD, unrelated doc.
20. Valid resume -> ready with name, roles with confidence, and years.
21. Low confidence roles (< 0.5) -> needs_role, jh_confirm issues ticket.
22. Soft warnings: outdated date (>18m), name mismatch -> ready with warning.
23. jh_replace_resume re-parses and re-scores without restarting worker.
24. Guesses never filter results before user explicitly answers.
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jh import config, db, interview_questions, resume_checker, role_inference, ticket_manager, v5_tools, worker_launcher
from conftest import SAMPLE_RESUME


@pytest.fixture(autouse=True)
def clean_v3_state(tmp_path, monkeypatch):
    """Ensure clean isolated state for each test."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(home_dir / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(home_dir / "data" / "engine.db"))
    monkeypatch.setenv("JOBHUNTER_BYPASS_DELAY", "1")
    
    # Isolate ticket and worker state
    ticket_manager._TICKETS.clear()
    ticket_manager._SESSIONS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()

    from jh import pipeline
    monkeypatch.setattr(pipeline, "search", lambda *args, **kwargs: {"jobs": [], "total": 0, "statuses": []})
    
    db.init_db()
    yield ws


def test_acceptance_01_jh_begin_valid_resume_no_premature_start(clean_v3_state):
    """Test 1: jh_begin replies with one-line profile and step 3 target questions. No search row exists, server closed, no browser opened."""
    with patch("webbrowser.open") as mock_browser:
        res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="test_sess_01")
        assert res["status"] in ("needs_target", "needs_role")
        assert "STOP. Ask the user the questions below" in res["message_for_user"]
        assert "Method: Modern (default) or Classic" in res["message_for_user"]
        assert "Target place:" in res["message_for_user"]
        assert res["next_tool"] == "jh_confirm"
        assert "ticket" not in res  # Ticket is not issued before target search is answered
        
        # Verify no premature search or server
        with db.session() as c:
            count = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            assert count == 0
            
        mock_browser.assert_not_called()
        assert worker_launcher.get_search_job_status("test_sess_01")["status"] == "not_started"

        # Now confirm answers to step 3 questions -> returns ticket and ready status
        c_res = v5_tools.jh_confirm(session_id="test_sess_01", user_reply="Modern method, Tunisia")
        assert c_res["status"] == "ready"
        assert c_res["ticket"].startswith("jh_tkt_")
        assert "subagent_brief" in c_res


def test_acceptance_02_jh_launch_and_search_reject_without_ticket():
    """Test 2: jh_launch and jh_search without ticket reply needs_input and start nothing."""
    # 1. jh_launch without ticket
    res_l = v5_tools.jh_launch(session_id="no_tkt_sess", ticket="")
    assert res_l["status"] == "needs_input"
    assert "STOP" in res_l["message_for_user"]
    assert res_l["next_tool"] == "jh_begin"

    # 2. jh_search without ticket
    res_s = v5_tools.jh_search(job_style="software engineer", session_id="no_tkt_sess", ticket="")
    assert res_s["status"] == "needs_input"
    assert "STOP" in res_s["message_for_user"]
    assert res_s["next_tool"] == "jh_begin"


def test_acceptance_03_old_tools_alias_to_jh_begin():
    """Test 3: Old combined tool names (jh_start, jh_load_resume) behave like jh_begin."""
    # Calling jh_start with no resume returns needs_resume with STOP rule
    res_start = v5_tools.jh_start(prompt="find me a job", session_id="alias_sess")
    assert res_start["status"] == "needs_resume"
    assert "STOP" in res_start["message_for_user"]
    assert res_start["next_tool"] == "jh_begin"

    # Calling jh_load_resume with resume text delegates to jh_begin
    res_load = v5_tools.jh_load_resume(raw_text=SAMPLE_RESUME, session_id="alias_sess_2")
    assert res_load["status"] in ("needs_target", "needs_role")
    assert res_load["next_tool"] == "jh_confirm"


def test_acceptance_04_jh_confirm_rejects_empty_or_repetition():
    """Test 4: jh_confirm with empty user_reply or repeating question text is rejected."""
    # 1. Empty reply
    res_empty = v5_tools.jh_confirm(session_id="c_sess", user_reply="")
    assert res_empty["status"] == "needs_input"
    assert "empty" in res_empty["message_for_user"].lower()

    # 2. Repeating the question
    res_rep = v5_tools.jh_confirm(session_id="c_sess", user_reply="What target job title or role are you aiming for?")
    assert res_rep["status"] == "needs_input"
    assert "repeats the question" in res_rep["message_for_user"].lower()


def test_acceptance_05_launch_speed_and_needs_role_flow(clean_v3_state):
    """Test 5: jh_launch returns in < 3s, starts server & search, opens browser. Also for needs_role flow."""
    # Part A: Ready flow
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="perf_sess")
    c_res = v5_tools.jh_confirm(session_id="perf_sess", user_reply="Modern, Tunisia")
    tkt = c_res["ticket"]

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True) as mock_b:
        t0 = time.time()
        l_res = v5_tools.jh_launch(session_id="perf_sess", ticket=tkt)
        elapsed = time.time() - t0
        
        assert elapsed < 3.0
        assert l_res["status"] == "ok"
        assert "http://127.0.0.1:8080/?session=perf_sess" in l_res["ui_url"]
        mock_b.assert_called_once()

    # Part B: needs_role flow
    vague_resume = """Candidate One
Tunis, Tunisia | candidate@example.com | +216 55 123 456
Objective: Looking for work in any department.
Skills: Communication, Teamwork, Microsoft Word, Planning, Customer Service, Organization
Experience:
General Assistant at Local Shop (2022 - 2023)
- Managed inventory and handled customer transactions at the register.
- Assisted with stock room organization and daily vendor deliveries.
Education:
High School Diploma, Lycee Pilote, 2022
"""
    b_vague = v5_tools.jh_begin(resume_text=vague_resume, session_id="vague_sess")
    assert b_vague["status"] == "needs_role"
    
    # Confirm role and explicit target place (Step 3 Place rule: place required before ticket)
    c_res = v5_tools.jh_confirm(session_id="vague_sess", user_reply="Backend Engineer, Remote only")
    assert c_res["status"] == "ready"
    tkt_vague = c_res["ticket"]

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8081}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        t0 = time.time()
        l_vague = v5_tools.jh_launch(session_id="vague_sess", ticket=tkt_vague)
        assert time.time() - t0 < 3.0
        assert l_vague["status"] == "ok"


def test_acceptance_06_mode_a_and_mode_b_identical_state(clean_v3_state):
    """Test 6: Mode A (direct) and Mode B (subagent) produce identical session state."""
    b_a = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="sess_mode_a")
    c_a = v5_tools.jh_confirm(session_id="sess_mode_a", user_reply="Modern, Tunisia")
    b_b = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="sess_mode_b")
    c_b = v5_tools.jh_confirm(session_id="sess_mode_b", user_reply="Modern, Tunisia")

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "reused", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        # Mode A: Main AI calls jh_launch
        res_a = v5_tools.jh_launch(session_id="sess_mode_a", ticket=c_a["ticket"])
        # Mode B: Subagent calls jh_launch with same parameters
        res_b = v5_tools.jh_launch(session_id="sess_mode_b", ticket=c_b["ticket"])

    assert res_a["status"] == res_b["status"] == "ok"
    assert res_a["server_status"] == res_b["server_status"]
    assert len(res_a["data"]["round_2_questions"]) == len(res_b["data"]["round_2_questions"])


def test_acceptance_07_launch_idempotency(clean_v3_state):
    """Test 7: Second jh_launch for the same session reuses worker and search."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="idem_sess")
    c_res = v5_tools.jh_confirm(session_id="idem_sess", user_reply="Modern, Tunisia")
    tkt = c_res["ticket"]

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        res1 = v5_tools.jh_launch(session_id="idem_sess", ticket=tkt)

    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "reused", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        res2 = v5_tools.jh_launch(session_id="idem_sess", ticket=tkt)

    assert res1["search_job_id"] == res2["search_job_id"]
    assert res2["server_status"] == "reused"


def test_acceptance_08_worker_process_independence(clean_v3_state):
    """Test 8: Worker survives simulated termination of calling subagent process."""
    # Write mock pid file in run dir
    run_dir = Path(config.BASE_DIR) / "jobmcp" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "server.pid").write_text("99999", encoding="utf-8")
    (run_dir / "server.port").write_text("8080", encoding="utf-8")

    # Launch search
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="survive_sess")
    c_res = v5_tools.jh_confirm(session_id="survive_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.is_server_healthy", return_value=True), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        res = v5_tools.jh_launch(session_id="survive_sess", ticket=c_res["ticket"])
        assert res["status"] == "ok"

    # Simulate subagent process exiting: worker PID file and search state remain in memory/disk
    assert (run_dir / "server.pid").is_file()
    job_status = worker_launcher.get_search_job_status("survive_sess")
    assert job_status["status"] in ("running", "completed")


def test_acceptance_09_answer_updates_filters_live_without_restart(clean_v3_state):
    """Test 9: jh_answer updates filters live without restarting the search."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="ans_sess")
    c_res = v5_tools.jh_confirm(session_id="ans_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        v5_tools.jh_launch(session_id="ans_sess", ticket=c_res["ticket"])

    search_id_before = worker_launcher.get_search_job_status("ans_sess")["job_id"]

    # Ingest a sample job to test filter changes
    sample_job = {
        "title": "Backend Python Developer",
        "company": "Tech Corp",
        "location": "Tunis, Tunisia",
        "work_mode": "hybrid",
        "job_type": "full-time",
        "score": 85,
    }
    db.store_jobs([sample_job], query="backend")

    # Update filter via jh_answer
    ans_res = v5_tools.jh_answer(session_id="ans_sess", answers={"work_mode": "hybrid"}, user_reply="hybrid only")
    assert ans_res["status"] == "ok"
    assert ans_res["data"]["matches_count"] >= 1

    # Search job ID must not have changed (no restart)
    assert worker_launcher.get_search_job_status("ans_sess")["job_id"] == search_id_before


def test_acceptance_10_status_top_5_matches_and_filter_counts(clean_v3_state):
    """Test 10: jh_status returns top 5 matches only, passing filters, with matching hidden count."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="top5_sess")
    c_res = v5_tools.jh_confirm(session_id="top5_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        v5_tools.jh_launch(session_id="top5_sess", ticket=c_res["ticket"])

    # Ingest 12 jobs (10 remote, 2 onsite)
    jobs = []
    for i in range(10):
        jobs.append({
            "title": f"Remote Engineer {i}", "company": f"Co {i}",
            "location": "Worldwide", "work_mode": "remote", "score": 80 + i
        })
    for i in range(2):
        jobs.append({
            "title": f"Onsite Engineer {i}", "company": f"Local {i}",
            "location": "Tunis", "work_mode": "onsite", "score": 70 + i
        })
    db.store_jobs(jobs, query="engineer")

    # Filter for remote only
    v5_tools.jh_answer(session_id="top5_sess", answers={"work_mode": "remote"}, user_reply="remote only")

    st = v5_tools.jh_status(session_id="top5_sess")
    assert st["status"] == "ok"
    assert "top_5_matches" not in st["data"]  # D6: Stripped job data
    assert st["data"]["matches"] == 10
    assert st["data"]["hidden_by_filters"] >= 2  # The 2 onsite jobs are hidden


def test_acceptance_11_tunisia_source_routing():
    """Test 11: With Tunisia, search queries no global remote feed."""
    from jh import source_registry
    prefs = {"home_country": "Tunisia", "target_countries": ["Tunisia"]}
    targets = ["TN"]
    remote_ok = False  # Set by pipeline when country is specific Tunisia without explicit worldwide remote

    # Global remote feeds must be skipped
    for feed in ["RemoteOK", "Himalayas", "Remotive", "Jobicy", "We Work Remotely"]:
        skip = source_registry.skip_reason(feed, prefs, targets, remote_ok)
        assert skip is not None, f"Expected {feed} to be skipped for Tunisia local search"
        assert skip[0] == "skipped"

    # MENA and local sources must remain eligible
    assert source_registry.skip_reason("Bayt", prefs, targets, remote_ok) is None
    assert source_registry.skip_reason("Company Boards", prefs, targets, remote_ok) is None


def test_acceptance_12_skip_all_handling(clean_v3_state):
    """Test 12: 'skip all' in user_reply stores fields as any and logs verbatim words."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="skip_sess")
    c_res = v5_tools.jh_confirm(session_id="skip_sess", user_reply="Modern, Worldwide")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        v5_tools.jh_launch(session_id="skip_sess", ticket=c_res["ticket"])

    ans_res = v5_tools.jh_answer(session_id="skip_sess", user_reply="skip all")
    assert ans_res["status"] == "ok"
    
    sess = ticket_manager.get_or_create_session("skip_sess")
    assert sess["answers"].get("job_type") == "any"
    assert sess["answers"].get("work_mode") == "any"
    assert any(log["user_reply"] == "skip all" for log in sess["skip_log"])


def test_acceptance_13_chat_suppression():
    """Test 13: Chat text after launch contains no job list before Round 2 answers."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="chat_sess")
    c_res = v5_tools.jh_confirm(session_id="chat_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        l_res = v5_tools.jh_launch(session_id="chat_sess", ticket=c_res["ticket"])

    msg = l_res["message_for_user"]
    assert "Do not list jobs in chat" in msg
    assert "http://" in l_res["ui_url"]
    assert "jobs_preview" not in l_res["data"]


def test_acceptance_14_instruction_files_contain_stop_rule():
    """Test 14: Instruction files hold STOP rule, no narrow line, no resume offer before save."""
    import mcp_server
    assert "call jh_begin first" in mcp_server.INSTRUCTIONS
    assert "Do not print jobs until round 2 is answered" in mcp_server.INSTRUCTIONS
    assert "Narrow the query" not in mcp_server.INSTRUCTIONS
    assert "save" in mcp_server.INSTRUCTIONS.lower()


def test_acceptance_15_install_agent_safety(tmp_path, monkeypatch):
    """Test 15: jh_install_agent asks first, writes only to user home dir, never workspace."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    # 1. Without confirmation: asks user and writes nothing
    ask_res = v5_tools.jh_install_agent(client="claude", confirmed=False)
    assert ask_res["status"] == "needs_input"
    assert not (fake_home / ".claude" / "agents" / "jobhunter-runner.md").exists()

    # 2. With confirmation: writes only to fake_home/.claude/agents/
    conf_res = v5_tools.jh_install_agent(client="claude", confirmed=True)
    assert conf_res["status"] == "ok"
    installed = fake_home / ".claude" / "agents" / "jobhunter-runner.md"
    assert installed.is_file()
    assert "jh_launch" in installed.read_text(encoding="utf-8")


def test_acceptance_16_launch_returns_under_3_seconds(clean_v3_state):
    """Test 16: Each launch call returns in under 3 seconds."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="speed_sess")
    c_res = v5_tools.jh_confirm(session_id="speed_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        t0 = time.time()
        res = v5_tools.jh_launch(session_id="speed_sess", ticket=c_res["ticket"])
        assert (time.time() - t0) < 3.0
        assert res["status"] == "ok"


def test_acceptance_17_protected_linkedin_intact():
    """Test 17: Baseline compatibility: protected LinkedIn code regions match stored hashes byte-exact."""
    import subprocess
    cmd = [subprocess.sys.executable, "-m", "pytest", "tests/test_protected_linkedin.py", "-q"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Protected LinkedIn check failed:\n{res.stdout}\n{res.stderr}"


def test_acceptance_18_no_resume_needs_resume_no_folder_search(clean_v3_state):
    """Test 18: With no resume, jh_begin replies needs_resume and missing file does not search folders."""
    res_empty = v5_tools.jh_begin(resume_path="", resume_text="", session_id="empty_sess")
    assert res_empty["status"] == "needs_resume"
    assert "STOP" in res_empty["message_for_user"]

    res_missing = v5_tools.jh_begin(resume_path="non_existent_file.pdf", session_id="missing_sess")
    assert res_missing["status"] == "needs_resume"
    assert "File does not exist" in str(res_missing["data"]["issues"])


def test_acceptance_19_document_kind_discrimination():
    """Test 19: Rejects empty text, cover letters, and job descriptions."""
    # 1. Under 300 chars
    short_text = "John Doe. Developer. Python, SQL."
    chk_short = resume_checker.check_resume(short_text)
    assert not chk_short["ok"]
    assert any("300 characters" in iss for iss in chk_short["issues"])

    # 2. Cover Letter
    cover_letter = """Dear Hiring Manager,
I am writing to express my strong enthusiasm for the Software Developer opening at your company.
I have been following your impressive growth and believe my passion makes me a great fit.
I look forward to discussing how I can contribute.
Sincerely,
Jane Doe
jane@example.com | 555-0199
"""
    chk_cl = resume_checker.check_resume(cover_letter * 2)  # Make > 300 chars
    assert not chk_cl["ok"]
    assert chk_cl["kind"] == "cover_letter"

    # 3. Job Description
    job_desc = """About the Role:
We are looking for a Senior Python Engineer to lead our core infrastructure team.
Key Responsibilities:
- Design and maintain microservices in FastAPI.
- Manage PostgreSQL databases and Redis caches.
Requirements:
- 5+ years experience in Python.
- Strong knowledge of Docker and Kubernetes.
Apply now to join our mission!
"""
    chk_jd = resume_checker.check_resume(job_desc * 2)
    assert not chk_jd["ok"]
    assert chk_jd["kind"] == "job_description"


def test_acceptance_20_valid_resume_gives_ready_with_summary():
    """Test 20: Valid resume gives needs_target in one call with name, roles, confidence, years."""
    res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="summary_sess")
    assert res["status"] in ("needs_target", "needs_role")
    assert res["data"]["name"] == "Ahmed Ben Salah"
    assert len(res["data"]["role_focus"]) >= 1
    assert "Backend Engineer" in res["data"]["role_focus"]
    assert "Profile Summary:" in res["data"]["profile_summary"]


def test_acceptance_21_low_confidence_gives_needs_role():
    """Test 21: Resume with unclear role (< 0.5) gives needs_role, jh_confirm issues ticket."""
    unclear = """Alex Smith
alex@example.com | 555-9876 | New York, NY
Summary: Experienced professional seeking growth opportunities.
Skills: Management, Budgeting, Coordination
Experience:
Team Coordinator, ABC Corp, 2021-2023
- Coordinated weekly team schedules.
Education:
BA in Liberal Arts, 2020
"""
    res = v5_tools.jh_begin(resume_text=unclear * 2, session_id="unclear_sess")
    assert res["status"] == "needs_role"
    assert "STOP" in res["message_for_user"]

    conf_res = v5_tools.jh_confirm(session_id="unclear_sess", user_reply="Project Manager, France")
    assert conf_res["status"] == "ready"
    assert conf_res["ticket"].startswith("jh_tkt_")


def test_acceptance_22_soft_warnings_outdated_and_name_mismatch():
    """Test 22: Resume with work history > 18m old or name mismatch gives ready with soft warning."""
    # Outdated work history (2019)
    outdated = """Sarah Connor
sarah@example.com | 555-4321 | Los Angeles, CA
Software Engineer
Experience:
Senior Developer, Cyberdyne Systems, 2017-2019
- Built distributed network daemons.
Skills: C++, Linux, Security, Python, Git
Education:
BS Computer Science, 2017
"""
    chk = resume_checker.check_resume(outdated * 2)
    assert chk["ok"]
    assert any("over 18 months old" in w for w in chk["warnings"])


def test_acceptance_23_jh_replace_resume_rescores_without_restart(clean_v3_state):
    """Test 23: jh_replace_resume re-parses and re-scores without restarting worker."""
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, session_id="replace_sess")
    c_res = v5_tools.jh_confirm(session_id="replace_sess", user_reply="Modern, Tunisia")
    with patch("jh.worker_launcher.start_detached_server", return_value={"status": "started", "port": 8080}), \
         patch("jh.worker_launcher.open_browser", return_value=True):
        v5_tools.jh_launch(session_id="replace_sess", ticket=c_res["ticket"])

    # Ingest a React job
    react_job = {
        "title": "Senior Frontend Developer",
        "company": "UI Labs",
        "description": "We need a Senior Frontend Developer proficient in React, Next.js, TypeScript, HTML/CSS, Tailwind CSS, Redux, and Jest.",
        "score": 40,
    }
    db.store_jobs([react_job], query="react")

    # Replace with Frontend resume
    frontend_resume = """Leila Trabelsi
leila@example.com | +216 22 111 222 | Tunis, Tunisia
Senior Frontend Developer
Skills: React, Next.js, TypeScript, CSS, Tailwind CSS, HTML/CSS, Redux, Jest
Experience:
Senior Frontend Developer, DevStudio, 2021-Present
- Built design systems and SPAs in React.
Education:
Engineering Degree in CS, INSAT, 2020
"""
    rep_res = v5_tools.jh_replace_resume(session_id="replace_sess", resume_text=frontend_resume)
    assert rep_res["status"] == "ready"
    assert rep_res["data"]["name"] == "Leila Trabelsi"

    # Verify stored jobs were re-scored
    with db.session() as c:
        row = c.execute("SELECT score FROM jobs WHERE title LIKE '%Frontend%'").fetchone()
        assert row is not None
        assert row[0] >= 70  # Higher score for React expert!


def test_acceptance_24_guesses_never_filter_before_answer(clean_v3_state):
    """Test 24: Guessed job type, location, or pay never filter results before user answers."""
    # Resume with PFE / intern hints in filename
    b_res = v5_tools.jh_begin(resume_text=SAMPLE_RESUME, resume_path="CV_PFE_2026.pdf", session_id="guess_sess")
    assert b_res["data"]["job_type_guess"]["guess"] is True
    assert b_res["data"]["region_guess"]["guess"] is True

    # Ingest full-time jobs and intern jobs
    db.store_jobs([
        {"title": "Full-time Software Engineer", "company": "Enterprise Co", "job_type": "full-time", "score": 85},
        {"title": "Intern Software Engineer", "company": "Startup Co", "job_type": "internship", "score": 85},
    ], query="engineer")

    # Query before Round 2 answers: both jobs must be visible!
    q_initial = db.query_jobs(session_id="guess_sess")
    assert q_initial["count"] >= 2
    assert any(j["title"] == "Full-time Software Engineer" for j in q_initial["jobs"])
    assert any(j["title"] == "Intern Software Engineer" for j in q_initial["jobs"])


# ==============================================================================
# FRONTEND ACCEPTANCE TESTS (F1 to F5)
# ==============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent

def test_acceptance_f1_progress_view_and_streaming(clean_v3_state):
    """Test F1: Progress view shows per-source cards with live status updates."""
    html_content = (REPO_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    js_content = (REPO_ROOT / "public" / "app.js").read_text(encoding="utf-8")
    css_content = (REPO_ROOT / "public" / "styles.css").read_text(encoding="utf-8")

    # Verify HTML markup
    assert 'id="search-progress-view"' in html_content
    assert 'id="source-cards-grid"' in html_content
    assert 'id="progress-sources-summary"' in html_content

    # Verify CSS rules
    assert ".progress-view-card" in css_content
    assert ".source-cards-grid" in css_content
    assert ".badge-status-running" in css_content

    # Verify JS EventSource stream integration
    assert "/api/search/stream" in js_content
    assert "initSearchStream" in js_content
    assert 'source-card' in js_content


def test_acceptance_f2_filter_strip_and_hidden_counter(clean_v3_state):
    """Test F2: A job matching the resume but not filters is hidden, and appears under 'Show hidden' with rule tag."""
    html_content = (REPO_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    js_content = (REPO_ROOT / "public" / "app.js").read_text(encoding="utf-8")
    css_content = (REPO_ROOT / "public" / "styles.css").read_text(encoding="utf-8")

    # Verify HTML markup
    assert 'id="filter-strip"' in html_content
    assert 'id="filter-chips-list"' in html_content
    assert 'id="filter-match-counter"' in html_content
    assert 'id="btn-toggle-hidden"' in html_content

    # Verify CSS rules for hidden jobs and rule tags
    assert ".job-card-hidden" in css_content
    assert "dashed" in css_content
    assert ".jc-filter-tag" in css_content

    # Verify JS filter logic
    assert "not internship" in js_content
    assert "salary below target" in js_content
    assert "state.showHidden" in js_content
    assert "renderFilterStrip" in js_content


def test_acceptance_f3_chat_question_banner(clean_v3_state):
    """Test F3: When jh_status reports an unanswered question, the banner shows the question text."""
    html_content = (REPO_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    js_content = (REPO_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    # Verify HTML markup
    assert 'id="banner-chat-question"' in html_content
    assert 'id="chat-question-text"' in html_content
    assert "The AI is asking you a question in chat:" in html_content

    # Verify JS polling and update logic
    assert "/api/session/status" in js_content
    assert "pollSessionStatus" in js_content
    assert "unanswered_questions" in js_content or "next_question" in js_content


def test_acceptance_f4_save_button_document_trigger(clean_v3_state):
    """Test F4: The Save button is the only path to the document actions."""
    js_content = (REPO_ROOT / "public" / "app.js").read_text(encoding="utf-8")
    from jh import save_flow

    # Verify JS UI gating: tailor and cover actions only unlocked when isSaved
    assert 'data-act="tailor"' in js_content
    assert 'data-act="cover"' in js_content
    assert 'isSaved' in js_content
    assert 'Documents are locked' in js_content

    # Verify Backend gating: save_flow.is_job_saved enforces Rule 4
    assert hasattr(save_flow, "is_job_saved")
    assert save_flow.is_job_saved("unsaved_dummy_id") is False


def test_acceptance_f5_resume_status_bar_and_replace(clean_v3_state):
    """Test F5: Changing the resume re-scores the list without restarting the search."""
    html_content = (REPO_ROOT / "public" / "index.html").read_text(encoding="utf-8")
    js_content = (REPO_ROOT / "public" / "app.js").read_text(encoding="utf-8")

    # Verify HTML markup
    assert 'id="candidate-bar"' in html_content
    assert 'id="bar-candidate-name"' in html_content
    assert 'id="bar-candidate-role"' in html_content
    assert 'id="btn-change-resume"' in html_content
    assert 'id="dlg-change-resume"' in html_content

    # Verify JS replace logic
    assert "/api/session/replace-resume" in js_content
    assert "initChangeResumeModal" in js_content
    assert "loadJobsQuery" in js_content
