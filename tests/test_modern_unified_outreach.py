"""Tests for unified headless Hybrid discovery (Signal Radar + Multi-Board Search) and Hybrid application pack."""
from pathlib import Path

import pytest

from jh import config, contacts, db, lifecycle, radar, save_flow, ticket_manager, v5_tools, worker_launcher


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
def isolated_hybrid_env(tmp_path, monkeypatch):
    jh_home = tmp_path / "jobmcp_home"
    ws = tmp_path / "ws"
    (jh_home / "data").mkdir(parents=True)
    (jh_home / "outputs").mkdir(parents=True)
    ws.mkdir(parents=True)
    monkeypatch.setenv("JOBMCP_HOME", str(jh_home))
    monkeypatch.setenv("JOBHUNTER_HOME", str(jh_home))
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(config, "DATA_DIR", str(jh_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(jh_home / "data" / "state"))
    db.init_db()
    ticket_manager._SESSIONS.clear()
    ticket_manager._TICKETS.clear()
    worker_launcher._ACTIVE_SEARCH_JOBS.clear()
    yield tmp_path


def test_hybrid_jh_launch_runs_radar_and_multiboard_search_headlessly(monkeypatch):
    from jh import signals as _signals

    radar_calls = []
    board_calls = []
    monkeypatch.setattr(radar, "start_radar_worker", lambda: radar_calls.append(True) or True)
    monkeypatch.setattr(_signals, "poll_modern_signals", lambda **kw: {"discovered": 2, "new_ingested": 2})
    monkeypatch.setattr(
        worker_launcher,
        "start_background_search",
        lambda **kw: board_calls.append(kw) or {"search_job_id": "search_hyb_1", "status": "started"},
    )

    v5_tools.jh_begin(resume_text=RAYEN_RESUME, session_id="s_hyb_dual")
    conf = v5_tools.jh_confirm(user_reply="South Asia", session_id="s_hyb_dual")
    res = v5_tools.jh_launch(session_id="s_hyb_dual", ticket=conf["ticket"])

    assert res["status"] == "ok"
    assert res["data"]["method"] == "hybrid"
    assert len(radar_calls) == 1
    assert len(board_calls) == 1
    assert board_calls[0]["location"] == "South Asia"
    assert res["data"]["board_search_job_id"] == "search_hyb_1"

    db.ingest_job({
        "id": "job_sa_cloud_1",
        "title": "Cloud Software Intern",
        "company": "ScaleInfra",
        "location": "Bengaluru, India",
        "work_mode": "Onsite",
        "url": "https://scaleinfra.io/careers/intern",
        "description": "Python, Docker, Kubernetes CI/CD intern.",
    })
    st = v5_tools.jh_status(session_id="s_hyb_dual")
    assert st["data"]["method"] == "hybrid"
    assert st["data"]["total_jobs"] == 1
    assert st["data"]["matches"] >= 1
    assert st["data"]["top_matches"][0]["company"] == "ScaleInfra"
    assert "Stored Jobs: 1" in st["message_for_user"]


def test_contacts_domain_from_urls_skips_ats_boards_and_keeps_company_domain():
    assert contacts._domain_from_urls("https://boards.greenhouse.io/acme/jobs/123") == ""
    assert contacts._domain_from_urls("https://linkedin.com/jobs/view/999", "https://cloudscale.io/careers") == "cloudscale.io"
    assert contacts._domain_from_urls("https://www.linear.app") == "linear.app"


def test_hybrid_save_produces_full_ats_and_outreach_pack(monkeypatch):
    v5_tools.jh_begin(resume_text=RAYEN_RESUME, session_id="default")
    v5_tools.jh_confirm(user_reply="South Asia", session_id="default")

    job = {
        "id": "job_hybrid_cloud_1",
        "title": "Cloud Software Engineering Intern",
        "company": "HybridScale",
        "company_url": "https://hybridscale.io",
        "location": "Remote, India",
        "work_mode": "Remote",
        "url": "https://hybridscale.io/jobs/cloud-intern",
        "description": "Python, Docker, Kubernetes, FastAPI, CI/CD cloud intern.",
    }
    db.ingest_job(job)
    monkeypatch.setattr(
        lifecycle,
        "liveness_check",
        lambda url, job_id=None: {"url": url, "is_live": True, "status_code": 200, "reason": "ok"},
    )
    monkeypatch.setattr(
        contacts,
        "find_contacts",
        lambda signal_id_or_company, target_role="", company_size=None, company_url="", job_url="", company_domain="": {
            "contacts": [db.save_contact({
                "id": "cnt_hyb_1",
                "company": "HybridScale",
                "company_domain": "hybridscale.io",
                "name": "Aarav Mehta",
                "title": "Engineering Manager",
                "role": "Engineering Manager",
                "email": "aarav@hybridscale.io",
                "confidence": "Found",
                "email_confidence": "Found",
                "verified_mx": True,
                "source": "public_page",
            })],
            "notice": "",
        },
    )

    data = save_flow.handle_save_job(job["id"], force=True, background=False)
    assert data["status"] == "ok"
    assert data["method"] == "hybrid"
    assert data["saved"] is True
    assert Path(data["resume_path"]).is_file()
    assert Path(data["cover_letter_path"]).is_file()
    assert data["contacts"] and data["contacts"][0]["email"] == "aarav@hybridscale.io"
    assert data["brief"]["company"] == "HybridScale"
    assert Path(data["resume"]["resume_path"]).is_file()
    assert data["resume"]["size_kb"] <= 200
    assert data["email"]["success"] is True
    assert data["email"]["recipient_email"] == "aarav@hybridscale.io"
    assert len(data["email"]["body"].splitlines()) <= 4
