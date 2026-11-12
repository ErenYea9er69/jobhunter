import json
import os
import shutil
import tempfile
import pytest
from jh import config, db, home, save_flow, lifecycle


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Set up an isolated temporary workspace for testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()

    # Seed a basic master candidate profile
    master_profile = {
        "name": "Jane Developer",
        "target_title": "Senior Python Backend Engineer",
        "years_of_experience": 6,
        "skills": ["Python", "PostgreSQL", "FastAPI", "Docker", "AWS", "Redis", "Git"],
        "experience": [
            {
                "company": "Acme Cloud Corp",
                "role": "Senior Software Engineer",
                "start_date": "2021-01",
                "end_date": "2024-01",
                "bullets": [
                    "Engineered distributed REST APIs using Python and FastAPI serving 10M requests daily.",
                    "Optimized PostgreSQL database queries and configured Redis caching.",
                ],
            },
            {
                "company": "Beta Startup",
                "role": "Software Developer",
                "start_date": "2018-06",
                "end_date": "2020-12",
                "bullets": [
                    "Developed backend microservices and containerized workflows with Docker on AWS."
                ],
            },
        ],
        "education": [
            {
                "institution": "State University",
                "degree": "Bachelor of Science in Computer Science",
                "year": 2018,
            }
        ],
    }
    db.save_profile(master_profile, profile_id="master")

    yield test_home


def test_save_click_closed_posting_needs_confirm(monkeypatch):
    """T9: Click Save on closed posting -> asks 'This posting appears closed. Generate anyway? [Yes / Skip]'."""
    job = {
        "id": "job_closed_001",
        "title": "Backend Engineer",
        "company": "Closed Tech Inc",
        "url": "https://example.com/job/closed",
        "description": "Python FastAPI developer needed.",
    }
    db.ingest_job(job)

    # Mock liveness_check to report posting as closed
    monkeypatch.setattr(
        lifecycle,
        "liveness_check",
        lambda url, job_dict=None: {
            "url": url,
            "is_live": False,
            "status_code": 404,
            "reason": "HTTP 404",
            "cached": False,
        },
    )

    # Initial save without confirmation
    res = save_flow.handle_save_job(job["id"], force=False, confirm_closed=False)
    assert res["status"] == "needs_confirm"
    assert "This posting appears closed. Generate anyway?" in res["message"]
    assert "Yes" in res["options"]
    assert "Skip" in res["options"]

    # Verify no outputs generated yet
    outputs_dir = home.get_home() / "outputs"
    assert not any(outputs_dir.glob("job_closed_001*"))

    # When user confirms closed posting
    res_confirmed = save_flow.handle_save_job(job["id"], force=True, confirm_closed=True)
    assert res_confirmed["status"] == "ok"
    assert res_confirmed["saved"] is True
    assert os.path.exists(res_confirmed["resume_path"])
    assert os.path.exists(res_confirmed["cover_letter_path"])


def test_fit_score_below_60_gap_report():
    """T10: Fit score below 60 -> shows real gaps, interview talking track, 'Add This If True' list; asks 'Save anyway, or skip?'."""
    job_low_fit = {
        "id": "job_low_fit_001",
        "title": "Pediatric Neurosurgeon",
        "company": "Metro General Hospital",
        "url": "https://example.com/hospital/surgeon",
        "description": "Looking for Board Certified Surgeon in Neurosurgery, Clinical Medicine, Surgical Procedures, Anatomy, Pediatrics.",
    }
    db.ingest_job(job_low_fit)

    res = save_flow.handle_save_job(job_low_fit["id"], force=False)
    assert res["status"] == "low_fit"
    assert res["fit_score"] < 60
    assert "Save anyway, or skip?" in res["message"]
    assert "gap_report" in res
    assert "missing_requirements" in res["gap_report"]
    assert "talking_track" in res["gap_report"]
    assert "add_this_if_true" in res["gap_report"]

    # Verify outputs not generated for unforced low-fit save
    outputs_dir = home.get_home() / "outputs"
    assert not any(outputs_dir.glob("job_low_fit_001*"))

    # Force save bypasses threshold
    res_forced = save_flow.handle_save_job(job_low_fit["id"], force=True)
    assert res_forced["status"] == "ok"
    assert res_forced["saved"] is True
    assert os.path.exists(res_forced["resume_path"])


def test_fit_score_above_60_generates_documents():
    """T11: Fit score >= 60 -> generates tailored resume and cover letter in outputs/, links in UI."""
    job_high_fit = {
        "id": "job_high_fit_001",
        "title": "Senior Python Developer",
        "company": "DataTech Solutions",
        "url": "https://example.com/job/python-dev",
        "description": "Seeking Senior Python Developer skilled in Python, FastAPI, PostgreSQL, AWS, Docker.",
    }
    db.ingest_job(job_high_fit)

    res = save_flow.handle_save_job(job_high_fit["id"], force=False)
    assert res["status"] == "ok"
    assert res["saved"] is True
    assert res["fit_score"] >= 60
    assert os.path.exists(res["resume_path"])
    assert os.path.exists(res["cover_letter_path"])
    assert res["grounding"] == "passed"

    # Verify DB state: keep_flag = 1, delete_at is NULL, application row exists
    with db.session() as c:
        row = c.execute("SELECT keep_flag, delete_at FROM jobs WHERE id=?", (job_high_fit["id"],)).fetchone()
        assert row["keep_flag"] == 1
        assert row["delete_at"] is None

        app = c.execute("SELECT * FROM applications WHERE id=?", (res["application_id"],)).fetchone()
        assert app is not None
        assert app["status"] == "saved"
        assert app["fit_score"] == res["fit_score"]
        assert app["resume_path"] == res["resume_path"]


def test_grounding_audit_catches_and_repairs_invented_facts():
    """T12: Tailored draft with an invented tool or employer fails grounding check, gets repaired, re-audited, saved only when clean."""
    prof = db.get_profile()
    job = {
        "title": "Python Developer",
        "company": "DataTech Solutions",
        "description": "Python engineering role.",
    }

    # Draft with invented employer and invented tool
    bad_draft = (
        "I was the Chief Architect at NASA Quantum Division from 1992 to 1999.\n"
        "I have 15 years of experience using SuperQuantumLang to build satellites.\n"
        "At Acme Cloud Corp, I engineered distributed REST APIs using Python and FastAPI."
    )

    passed, clean_text, findings = save_flow.grounding_check_and_repair(
        bad_draft, prof, job, kind="cover_letter"
    )
    assert passed is True
    # The invented employer 'NASA Quantum Division' must be removed
    assert "NASA Quantum Division" not in clean_text
    assert "SuperQuantumLang" not in clean_text
    # Grounded fact about Acme Cloud Corp and FastAPI should be preserved
    assert "Acme Cloud Corp" in clean_text or "FastAPI" in clean_text or "Python" in clean_text


def test_dismiss_pattern_after_5_dismissals():
    """T13: Click dismiss 5 times -> UI suggests loosening or tuning view filters."""
    for i in range(4):
        res = save_flow.handle_dismiss_job(f"job_dismiss_{i}", reason="Salary too low")
        assert res["dismissed"] is True
        assert res["count"] == i + 1
        assert "proposal" not in res

    # 5th dismissal triggers pattern proposal
    res5 = save_flow.handle_dismiss_job("job_dismiss_4", reason="Pay below market rate")
    assert res5["dismissed"] is True
    assert res5["count"] == 5
    assert "proposal" in res5
    assert res5["proposal"]["type"] == "salary"
    assert res5["proposal"]["suggested_filter"] == "min_salary"
    assert "raise your minimum salary filter" in res5["message"].lower()


def test_generate_unsaved_job_rejected():
    """T14: Try generating for an unsaved job -> rejected (Rule 4: Generate on save only)."""
    assert save_flow.is_job_saved("non_existent_or_unsaved_job") is False

    # Mark a job saved
    job = {
        "id": "job_saved_test_001",
        "title": "Python Developer",
        "company": "Acme Partner",
        "url": "https://example.com/job/saved",
        "description": "Python developer role.",
    }
    db.ingest_job(job)
    with db.session() as c:
        c.execute("UPDATE jobs SET keep_flag=1 WHERE id=?", (job["id"],))

    assert save_flow.is_job_saved("job_saved_test_001") is True


def _call_http(method: str, path: str, body: dict = None) -> tuple[int, dict]:
    import io
    from pathlib import Path
    from jh.httpd import JobHunterRequestHandler

    class FakeServer:
        def __init__(self):
            self.ws_dir = Path.cwd()

    raw_body = json.dumps(body).encode("utf-8") if body else b""
    rfile = io.BytesIO(raw_body)
    wfile = io.BytesIO()

    handler = JobHunterRequestHandler.__new__(JobHunterRequestHandler)
    handler.rfile = rfile
    handler.wfile = wfile
    handler.server = FakeServer()
    handler.path = path
    handler.command = method
    handler.headers = {
        "Content-Length": str(len(raw_body)),
        "Content-Type": "application/json",
    }
    handler.close_connection = True

    status_code = [200]
    def mock_send_response(code, message=None):
        status_code[0] = code
    handler.send_response = mock_send_response
    handler.send_header = lambda k, v: None
    handler.end_headers = lambda: None

    if method == "POST":
        handler.do_POST()
    elif method == "GET":
        handler.do_GET()

    wfile.seek(0)
    output = wfile.read()
    parsed_json = json.loads(output.decode("utf-8")) if output else {}
    return status_code[0], parsed_json


def test_http_save_and_generate_api():
    """Verify HTTP endpoints for save, dismiss, and generate."""
    job = {
        "id": "http_job_001",
        "title": "Senior Python Backend Engineer",
        "company": "FastAPI Cloud",
        "url": "https://fastapi.example.com/job",
        "description": "Python, FastAPI, AWS, Docker backend engineer.",
    }
    db.ingest_job(job)

    # 1. POST /api/generate for unsaved job -> 400 error (Decision D)
    code, res = _call_http("POST", "/api/generate", {"job_id": job["id"]})
    assert code == 400
    assert res["status"] == "error"
    assert "saved jobs" in res["error"]["message"].lower()

    # 2. POST /api/jobs/save
    code, save_res = _call_http("POST", "/api/jobs/save", {"job_id": job["id"], "force": True})
    assert code == 200
    assert save_res["status"] == "ok"
    assert save_res["data"]["saved"] is True

    # 3. POST /api/generate for now-saved job -> succeeds
    code, gen_res = _call_http("POST", "/api/generate", {"job_id": job["id"]})
    assert code == 200
    assert gen_res["status"] == "ok"

    # 4. POST /api/jobs/dismiss
    code, dis_res = _call_http("POST", "/api/jobs/dismiss", {"job_id": job["id"], "reason": "Location mismatch"})
    assert code == 200
    assert dis_res["status"] == "ok"
    assert dis_res["data"]["dismissed"] is True
