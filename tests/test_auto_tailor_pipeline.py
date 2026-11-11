"""Tests for the selective search and auto-tailor application pipeline."""
import json
import time
import pytest
from jh import db, tracker, refit, pipeline, resume_registry


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_engine.db"
    monkeypatch.setattr("jh.config.DB_PATH", str(test_db))
    monkeypatch.setattr("jh.config.DATA_DIR", str(tmp_path))
    db.init_db()
    yield
    test_db.unlink(missing_ok=True)


def test_auto_tailor_application_populates_resume_and_cover_letter():
    # Setup candidate profile
    profile = {
        "name": "Rayen Ben Aissa",
        "email": "rayen@example.com",
        "phone": "+216 52213067",
        "location": "Tunisia",
        "target_title": "Full Stack Developer",
        "skills": ["Python", "FastAPI", "React", "PostgreSQL", "Supabase", "TypeScript", "REST APIs"],
        "experience": [
            {
                "role": "Full Stack Engineer",
                "company": "Tech Innovators",
                "bullets": ["Architected scalable web applications using FastAPI and React."]
            }
        ]
    }
    db.save_profile(profile, profile_id="var_rayen")
    db.set_active_resume_profile("var_rayen")

    job = {
        "id": "job-test-123",
        "title": "Full-Stack Engineer",
        "company": "Acme Cloud",
        "location": "Worldwide (Remote)",
        "description": "Looking for a Full-Stack Engineer with Python, React, and Supabase experience to build cloud systems."
    }

    # User saves the job
    app_id = tracker.upsert_application({
        "job_id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "status": "saved",
        "job_data": job
    })

    # Run auto-tailor synchronously
    tracker.auto_tailor_application(app_id, profile=profile, background=False)

    # Verify that tailored_resume and cover_letter are stored
    apps = tracker.list_applications()
    saved_app = next((a for a in apps if a["id"] == app_id), None)
    assert saved_app is not None
    assert saved_app["status"] == "saved"
    assert saved_app["tailored_resume"] is not None
    assert isinstance(saved_app["tailored_resume"], dict)
    assert saved_app["cover_letter"] is not None
    assert len(saved_app["cover_letter"]) > 50

    # Verify tailored variant is also registered in resume_profiles
    profiles = db.list_resume_profiles()
    tailored_prof = next((p for p in profiles if "var_tailored" in p.get("id", "")), None)
    assert tailored_prof is not None
    assert "Acme Cloud" in tailored_prof["name"]


def test_auto_tailor_application_async_background():
    profile = {
        "name": "Rayen Ben Aissa",
        "email": "rayen@example.com",
        "target_title": "Full Stack Developer",
        "skills": ["Python", "React", "Node.js"],
        "experience": [{"role": "Developer", "company": "Co", "bullets": ["Built APIs."]}]
    }
    db.save_profile(profile, profile_id="var_rayen")
    db.set_active_resume_profile("var_rayen")

    job = {
        "id": "job-async-456",
        "title": "Backend Engineer",
        "company": "CloudStream",
        "description": "Seeking Python backend developer with API design skills."
    }

    app_id = tracker.upsert_application({
        "job_id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "status": "saved",
        "job_data": job
    })

    # Trigger background thread
    th = tracker.auto_tailor_application(app_id, profile=profile, background=True)
    assert th is not None
    th.join(timeout=5.0)

    apps = tracker.list_applications()
    saved_app = next((a for a in apps if a["id"] == app_id), None)
    assert saved_app is not None
    assert saved_app["tailored_resume"] is not None
    assert saved_app["cover_letter"] is not None

