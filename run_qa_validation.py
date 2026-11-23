#!/usr/bin/env python3
"""End-to-End QA & Validation Script for JobHunter MCP & Web Application."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jh import config, db, home, httpd, worker_launcher
from jh.v5_tools import jh_begin, jh_launch, jh_answer

def run_e2e_qa():
    results = {}
    print("=" * 70)
    print("STARTING JOBHUNTER END-TO-END QA & VALIDATION")
    print("=" * 70)

    # Clean previous run state if any
    home.ensure_home_dirs()
    session_id = f"e2e_qa_session_{int(time.time())}"

    # --------------------------------------------------------------------------
    # Step 1: Execute jh_begin with realistic resume
    # --------------------------------------------------------------------------
    print("\n--- STEP 1: Execute jh_begin ---")
    resume_text = """Rayen Ben Aissa
Tunis, Tunisia | rayen.benaissa@email.com | +216 12 345 678 | linkedin.com/in/rayenbenaissa | github.com/rayenbenaissa

SUMMARY
Motivated Software Engineering student seeking a Cloud, Backend, or Full Stack Software Engineering Internship. Experienced with AWS, C#, Express, Python, JavaScript, Docker, and SQL databases.

EDUCATION
Higher Institute of Computer Science (ISI), Tunis
Bachelor of Science in Computer Science, Software Engineering | Expected: June 2027

SKILLS
Programming Languages: Python, JavaScript, TypeScript, C#, SQL
Frameworks & Libraries: Node.js, Express.js, React, FastAPI, ASP.NET Core
Cloud & DevOps: AWS (EC2, S3, Lambda), Docker, Git, CI/CD, Linux
Databases: PostgreSQL, MongoDB, MySQL

EXPERIENCE
Software Engineering Intern | Tech Solutions | Summer 2025
- Contributed to backend microservices development using Express, C#, and Python.
- Implemented RESTful endpoints and optimized database queries.

PROJECTS
Cloud Task Orchestrator | Python, AWS, Docker
- Built distributed task processing engine using AWS SQS and Lambda with Express REST APIs.
"""
    begin_resp = jh_begin(resume_text=resume_text, session_id=session_id)
    print("jh_begin status:", begin_resp.get("status"))
    print("jh_begin ticket:", begin_resp.get("ticket"))
    print("jh_begin step:", begin_resp.get("step"))
    print("jh_begin subagent_brief:", begin_resp.get("subagent_brief"))

    questions = begin_resp.get("options", {}).get("questions", [])
    q1 = next((q for q in questions if q.get("id") == "location"), {})
    q1_choices = q1.get("choices", [])
    q1_recommended = q1.get("recommended", "")
    q1_note = q1.get("note", "")

    print("Q1 (Location) Choices:", q1_choices)
    print("Q1 Recommended:", q1_recommended)
    print("Q1 Note:", q1_note)

    # Verification assertions for Step 1
    assert begin_resp.get("status") == "ready", f"Expected ready, got {begin_resp.get('status')}"
    assert begin_resp.get("ticket") is not None, "Expected valid ticket issued"
    assert "Tunisia" not in q1_recommended, f"Location recommendation should NOT be Tunisia, got {q1_recommended}"
    assert q1_recommended in ("Worldwide", "Remote worldwide"), f"Expected Worldwide/Remote worldwide, got {q1_recommended}"
    assert "Tunisia" != q1_choices[0], f"First choice should not be Tunisia, got {q1_choices}"
    print(">>> Step 1 PASSED: Ticket issued, Location defaults suggest Worldwide, Tunisia is NOT default.")
    results["step1"] = {"status": "PASSED", "ticket": begin_resp.get("ticket"), "recommended_location": q1_recommended}

    # --------------------------------------------------------------------------
    # Step 2: Execute jh_launch
    # --------------------------------------------------------------------------
    print("\n--- STEP 2: Execute jh_launch ---")
    ticket = begin_resp.get("ticket")
    launch_resp = jh_launch(session_id=session_id, ticket=ticket)

    print("jh_launch status:", launch_resp.get("status"))
    print("jh_launch ui_url:", launch_resp.get("ui_url"))
    print("jh_launch port:", launch_resp.get("data", {}).get("port"))
    print("jh_launch browser_opened:", launch_resp.get("data", {}).get("browser_opened"))

    ui_url = launch_resp.get("ui_url", "")
    port = launch_resp.get("data", {}).get("port")
    browser_opened = launch_resp.get("data", {}).get("browser_opened")

    # Verification assertions for Step 2
    assert launch_resp.get("status") == "ok", f"Expected ok, got {launch_resp.get('status')}"
    assert port is not None and port > 0, f"Expected valid port, got {port}"
    assert browser_opened is False, f"Expected browser_opened to be False, got {browser_opened}"
    assert "#/jobs" in ui_url, f"Expected ui_url to contain '#/jobs', got {ui_url}"
    print(f">>> Step 2 PASSED: Server started on port {port}, browser_opened is False, ui_url has '#/jobs'.")
    results["step2"] = {"status": "PASSED", "port": port, "ui_url": ui_url, "browser_opened": browser_opened}

    # Wait brief moment for daemon socket
    time.sleep(1.0)

    # --------------------------------------------------------------------------
    # Step 3: Execute jh_answer with exact prompt
    # --------------------------------------------------------------------------
    print("\n--- STEP 3: Execute jh_answer ---")
    user_prompt = """1. south asia(bc im in tunisa and it's kinda most free visa or easy one)
2. match my lvl
3. Internship or remote job(that match my skill)
4. remote
5. any
6. if they give visa why not, but mostly i want remote
7. any"""

    answer_resp = jh_answer(session_id=session_id, user_reply=user_prompt)
    print("jh_answer status:", answer_resp.get("status"))

    db_filters = db.get_view_filters(session_id)
    locations = db_filters.get("locations", [])
    work_mode = db_filters.get("work_mode", "")
    job_type = db_filters.get("job_style") or db_filters.get("roles", [])

    print("DB parsed locations:", locations)
    print("DB parsed work_mode:", work_mode)
    print("DB view filters full:", db_filters)

    # Verification assertions for Step 3
    assert "South Asia" in locations, f"Expected 'South Asia' in locations, got {locations}"
    assert "Tunisia" not in locations, f"Locations should NOT contain Tunisia, got {locations}"
    assert work_mode.lower() == "remote", f"Expected work_mode 'remote', got {work_mode}"
    print(">>> Step 3 PASSED: Locations filter includes 'South Asia' and is NOT overridden by 'Tunisia'.")
    results["step3"] = {"status": "PASSED", "locations": locations, "work_mode": work_mode}

    # --------------------------------------------------------------------------
    # Step 4: Test HTTP endpoints directly using urllib.request
    # --------------------------------------------------------------------------
    print("\n--- STEP 4: Test running HTTP endpoints ---")
    base_url = f"http://127.0.0.1:{port}"

    # 4a. GET /api/signals with session
    url_signals = f"{base_url}/api/signals?session={session_id}"
    print(f"Testing GET {url_signals}...")
    req_sig = urllib.request.Request(url_signals)
    with urllib.request.urlopen(req_sig, timeout=10) as resp:
        assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
        body_bytes = resp.read()
        sig_data = json.loads(body_bytes.decode("utf-8"))
        assert sig_data.get("status") == "ok", f"Expected status 'ok', got {sig_data.get('status')}"
        assert "signals" in sig_data.get("data", {}), "Expected 'signals' field in data"
        print("  GET /api/signals OK: HTTP 200, valid JSON response with signals count:", len(sig_data["data"]["signals"]))
    results["step4_signals"] = {"status": "PASSED", "code": 200, "count": len(sig_data["data"]["signals"])}

    # 4b. POST /api/jobs/query with JSON body
    url_jobs_query = f"{base_url}/api/jobs/query"
    print(f"Testing POST {url_jobs_query}...")
    post_payload = json.dumps({"session_id": session_id}).encode("utf-8")
    req_jobs_post = urllib.request.Request(
        url_jobs_query,
        data=post_payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_jobs_post, timeout=10) as resp:
        assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
        jobs_data_post = json.loads(resp.read().decode("utf-8"))
        assert jobs_data_post.get("status") == "ok", f"Expected status 'ok', got {jobs_data_post.get('status')}"
        assert "results" in jobs_data_post.get("data", {}), "Expected 'results' in data"
        print("  POST /api/jobs/query OK: HTTP 200, valid JSON, results count:", jobs_data_post["data"]["count"])
    results["step4_jobs_query_post"] = {"status": "PASSED", "code": 200, "count": jobs_data_post["data"]["count"]}

    # 4c. GET /api/jobs/query with query parameter
    url_jobs_get = f"{base_url}/api/jobs/query?session={session_id}"
    print(f"Testing GET {url_jobs_get}...")
    with urllib.request.urlopen(url_jobs_get, timeout=10) as resp:
        assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
        jobs_data_get = json.loads(resp.read().decode("utf-8"))
        assert jobs_data_get.get("status") == "ok", f"Expected status 'ok', got {jobs_data_get.get('status')}"
        assert "results" in jobs_data_get.get("data", {}), "Expected 'results' in data"
        print("  GET /api/jobs/query OK: HTTP 200, valid JSON, results count:", jobs_data_get["data"]["count"])
    results["step4_jobs_query_get"] = {"status": "PASSED", "code": 200, "count": jobs_data_get["data"]["count"]}

    # 4d. GET / or /index.html
    url_index = f"{base_url}/"
    print(f"Testing GET {url_index}...")
    with urllib.request.urlopen(url_index, timeout=10) as resp:
        assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
        html_text = resp.read().decode("utf-8")
        assert len(html_text) > 500, f"HTML content too short: {len(html_text)}"
        assert "<!DOCTYPE html>" in html_text or "<html" in html_text, "Not valid HTML"
        assert "JobHunter" in html_text, "Expected 'JobHunter' in HTML title/body"
        print(f"  GET / OK: HTTP 200, HTML loaded successfully ({len(html_text)} bytes).")
    results["step4_index_html"] = {"status": "PASSED", "code": 200, "size": len(html_text)}

    # 4e. GET /app.js
    url_appjs = f"{base_url}/app.js"
    print(f"Testing GET {url_appjs}...")
    with urllib.request.urlopen(url_appjs, timeout=10) as resp:
        assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
        js_text = resp.read().decode("utf-8")
        assert len(js_text) > 1000, f"JS content too short: {len(js_text)}"
        assert "const" in js_text or "function" in js_text or "state" in js_text, "Not valid JS"
        print(f"  GET /app.js OK: HTTP 200, JavaScript loaded successfully ({len(js_text)} bytes).")
    results["step4_app_js"] = {"status": "PASSED", "code": 200, "size": len(js_text)}

    # --------------------------------------------------------------------------
    # Step 5: Edge cases and health checks
    # --------------------------------------------------------------------------
    print("\n--- STEP 5: Additional Edge Case Checks ---")
    # Health endpoint
    url_health = f"{base_url}/health"
    with urllib.request.urlopen(url_health, timeout=5) as resp:
        health_data = json.loads(resp.read().decode("utf-8"))
        print("  GET /health status:", health_data.get("status"))
        assert health_data.get("status") in ("ok", "healthy")
    results["step5_health"] = {"status": "PASSED", "code": 200}

    # Radar status endpoint with view_filters
    url_radar = f"{base_url}/api/radar/status"
    with urllib.request.urlopen(url_radar, timeout=5) as resp:
        radar_data = json.loads(resp.read().decode("utf-8"))
        print("  GET /api/radar/status:", radar_data.get("data", {}).get("status"))
        assert radar_data.get("status") == "ok"

    print("\n" + "=" * 70)
    print("ALL END-TO-END QA TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)
    return results

if __name__ == "__main__":
    res = run_e2e_qa()
    print("\nSUMMARY RESULTS JSON:")
    print(json.dumps(res, indent=2))
