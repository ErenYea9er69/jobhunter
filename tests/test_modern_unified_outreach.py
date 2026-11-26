"""Tests for unified Modern discovery (Signal Radar + Multi-Board Search) and direct-outreach Job Save."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from jh import config, contacts, db, lifecycle, radar, save_flow, ticket_manager, v5_tools, worker_launcher
from jh.httpd import JobHunterRequestHandler


RAYEN_RESUME = """Rayen Ben Aissa
rayen@example.com | linkedin.com/in/rayen-ba

SUMMARY
Cloud Software Engineering student building Docker, Kubernetes, and FastAPI systems.

SKILLS
Python, FastAPI, Docker, Kubernetes, CI/CD, GitHub Actions, PostgreSQL, Linux

TECHNICAL PROJECTS
CloudPipeline | Docker, Kubernetes, Python
- Built automated Kubernetes and Docker CI/CD pipelines with zero-downtime rollouts.
MyNet | FastAPI, Docker
- Built an observability dashboard API with Prometheus and Docker Compose.
"""


@pytest.fixture(autouse=True)
def isolated_modern_env(tmp_path, monkeypatch):
    jh_home = tmp_path / "jobmcp_home"
    ws = tmp_path / "ws"
    (jh_home / "data").mkdir(parents=True)
    (jh_home / "outputs").mkdir(parents=True)
    ws.mkdir(parents=True)
    monkeypatch.setenv("JOBMCP_HOME", str(jh_home))
    monkeypatch.setenv("JOBHUNTER_HOME", str(jh_home))
    monkeypatch.setenv("JOBHUNTER_NO_BROWSER", "1")
    monkeypatch.setenv("JOBHUNTER_BYPASS_DELAY", "1")
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(jh_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(jh_home / "data" / "engine.db"))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    yield tmp_path


def _call_http(method: str, path: str, payload: dict | None = None):
    captured = {}
    handler = object.__new__(JobHunterRequestHandler)
    handler.server = SimpleNamespace(ws_dir=Path.cwd())
    raw_body = json.dumps(payload or {}).encode("utf-8") if payload is not None else b""
    handler.headers = {"Content-Length": str(len(raw_body)), "Content-Type": "application/json"}
    handler.rfile = io.BytesIO(raw_body)
    handler.path = path
    handler.client_address = ("127.0.0.1", 51234)
    handler._send_json = lambda code, obj: captured.update({"code": code, "body": obj})
    handler._send_file = lambda *a, **kw: None
    if method == "POST":
        handler.do_POST()
    else:
        handler.do_GET()
    return captured["code"], captured["body"]


def test_modern_jh_launch_runs_radar_and_multiboard_search_and_status_shows_both(monkeypatch):
    from jh import signals as _signals

    radar_calls = []
    board_calls = []
    monkeypatch.setattr(worker_launcher, "start_detached_server", lambda *a, **kw: {"status": "started", "port": 8080})
    monkeypatch.setattr(worker_launcher, "open_browser", lambda *a, **kw: False)
    monkeypatch.setattr(radar, "start_radar_worker", lambda: radar_calls.append(True) or True)
    monkeypatch.setattr(_signals, "poll_modern_signals", lambda **kw: {"discovered": 2, "new_ingested": 2})
    monkeypatch.setattr(
        worker_launcher,
        "start_background_search",
        lambda **kw: board_calls.append(kw) or {"search_job_id": "search_mod_1", "status": "started"},
    )

    v5_tools.jh_begin(resume_text=RAYEN_RESUME, session_id="s_mod_dual")
    conf = v5_tools.jh_confirm(user_reply="modern, South Asia", session_id="s_mod_dual")
    res = v5_tools.jh_launch(session_id="s_mod_dual", ticket=conf["ticket"])

    assert res["status"] == "ok"
    assert "#/signals" in res["ui_url"]
    assert len(radar_calls) == 1
    assert len(board_calls) == 1
    assert board_calls[0]["location"] == "South Asia"
    assert res["data"]["board_search_job_id"] == "search_mod_1"

    db.ingest_job({
        "id": "job_sa_cloud_1",
        "title": "Cloud Software Intern",
        "company": "ScaleInfra",
        "location": "Bengaluru, India",
        "work_mode": "Onsite",
        "url": "https://scaleinfra.io/careers/intern",
        "description": "Python, Docker, Kubernetes CI/CD intern.",
    })
    st = v5_tools.jh_status(session_id="s_mod_dual")
    assert st["data"]["method"] == "modern"
    assert st["data"]["total_jobs"] == 1
    assert st["data"]["matches"] >= 1
    assert "Stored Jobs: 1" in st["message_for_user"]


def test_contacts_domain_from_urls_skips_ats_boards_and_keeps_company_domain():
    assert contacts._domain_from_urls("https://boards.greenhouse.io/acme/jobs/123") == ""
    assert contacts._domain_from_urls("https://linkedin.com/jobs/view/999", "https://cloudscale.io/careers") == "cloudscale.io"
    assert contacts._domain_from_urls("https://www.linear.app") == "linear.app"


def test_modern_jobs_save_produces_contacts_brief_pdf_and_cold_email_without_cover_letter(monkeypatch):
    v5_tools.jh_begin(resume_text=RAYEN_RESUME, session_id="default")
    v5_tools.jh_confirm(user_reply="modern, South Asia", session_id="default")

    job = {
        "id": "job_modern_cloud_1",
        "title": "Cloud Software Engineering Intern",
        "company": "CloudScale",
        "company_url": "https://cloudscale.io",
        "location": "Remote, India",
        "work_mode": "Remote",
        "url": "https://cloudscale.io/jobs/cloud-intern",
        "description": "Hiring Cloud Software Engineering Intern with Python, Docker, Kubernetes, CI/CD, and FastAPI.",
    }
    db.ingest_job(job)

    monkeypatch.setattr(
        lifecycle,
        "liveness_check",
        lambda url, job_id=None: {"url": url, "is_live": True, "status_code": 200, "reason": "ok"},
    )
    def _fake_find_contacts(signal_id_or_company, target_role="", company_size=None, company_url="", job_url="", company_domain=""):
        saved = db.save_contact({
            "id": "cnt_hr_1",
            "company": "CloudScale",
            "company_domain": "cloudscale.io",
            "name": "Priya Nair",
            "title": "Head of Engineering",
            "role": "Head of Engineering",
            "email": "priya@cloudscale.io",
            "confidence": "Found",
            "email_confidence": "Found",
            "verified_mx": True,
            "source": "public_page",
        })
        return {"contacts": [saved], "notice": ""}

    monkeypatch.setattr(contacts, "find_contacts", _fake_find_contacts)

    code, body = _call_http("POST", "/api/jobs/save", {"job_id": job["id"], "force": False})
    assert code == 200
    assert body["status"] == "ok"
    data = body["data"]
    assert data["method"] == "modern"
    assert data["saved"] is True
    assert data["contacts"] and data["contacts"][0]["email"] == "priya@cloudscale.io"
    assert data["brief"]["company"] == "CloudScale"
    assert Path(data["resume"]["resume_path"]).is_file()
    assert data["resume"]["size_kb"] <= 200
    assert "cover_letter_path" not in data
    assert data["email"]["success"] is True
    assert data["email"]["recipient_email"] == "priya@cloudscale.io"
    assert len(data["email"]["body"].splitlines()) <= 4

    with db.session() as c:
        row = c.execute("SELECT saved_by, keep_flag FROM jobs WHERE id=?", (job["id"],)).fetchone()
        assert row["saved_by"] == "ui" and row["keep_flag"] == 1
        out_rows = c.execute("SELECT company, recipient_email FROM outreach").fetchall()
        assert any(r["company"] == "CloudScale" and r["recipient_email"] == "priya@cloudscale.io" for r in out_rows)


def test_classic_jobs_save_keeps_tailored_resume_and_cover_letter(monkeypatch):
    v5_tools.jh_begin(resume_text=RAYEN_RESUME, session_id="default")
    v5_tools.jh_confirm(user_reply="classic, France", session_id="default")

    job = {
        "id": "job_classic_cloud_1",
        "title": "Cloud Software Engineering Intern",
        "company": "ParisTech",
        "location": "Paris, France",
        "url": "https://paristech.fr/jobs/1",
        "description": "Python, Docker, Kubernetes, FastAPI internship in Paris.",
    }
    db.ingest_job(job)
    monkeypatch.setattr(
        lifecycle,
        "liveness_check",
        lambda url, job_id=None: {"url": url, "is_live": True, "status_code": 200, "reason": "ok"},
    )

    code, body = _call_http("POST", "/api/jobs/save", {"job_id": job["id"], "force": False})
    assert code == 200
    data = body["data"]
    assert data["method"] == "classic"
    assert Path(data["resume_path"]).is_file()
    assert Path(data["cover_letter_path"]).is_file()


def test_webapp_and_public_synced_and_modern_hides_extension_apply():
    for fname in ("app.js", "index.html", "styles.css"):
        assert Path("webapp", fname).read_bytes() == Path("public", fname).read_bytes()
    js = Path("webapp/app.js").read_text(encoding="utf-8")
    assert "Save &amp; Find Contacts" in js
    assert "Find Contacts &amp; Email" in js
    assert 'openContactsPanel(res, { company: j.company, role_guess: j.title, url: jobUrl(j), is_job: true })' in js
