"""Tests for Step 1: Calibration, Scoping Protocol, and Job Type Filtering."""
from pathlib import Path
from jh import pipeline, preferences, workspace
from jh.team import router


def test_router_extracts_job_types():
    p1 = router.parse("find full-time backend engineer jobs in Tunisia")
    assert p1.job_types == ["Full-time"]
    assert p1.role == "backend engineer"
    assert "Tunisia" in p1.location

    p2 = router.parse("search for python internship in Tunis")
    assert p2.job_types == ["Internship"]
    assert p2.role == "python"

    p3 = router.parse("set me up. I want remote fulltime work in Tunisia")
    assert "Full-time" in p3.job_types
    assert p3.work_mode == "Remote"
    assert any("Tunisia" in c for c in p3.countries)


def test_pipeline_passes_filters_job_types():
    job_fulltime = {
        "title": "Senior Backend Engineer",
        "job_type": "Full-time",
        "location": "Tunis, Tunisia",
        "work_mode": "Hybrid",
        "country": "Tunisia",
    }
    job_internship = {
        "title": "Software Engineering Intern",
        "job_type": "Internship",
        "location": "Tunis, Tunisia",
        "work_mode": "Hybrid",
        "country": "Tunisia",
    }
    job_stage_french = {
        "title": "Stage PFE - Développeur Python",
        "job_type": "",
        "location": "Tunis, Tunisia",
        "work_mode": "Onsite",
        "country": "Tunisia",
    }

    # When user prefers Full-time only: internships are rejected
    assert pipeline._passes(job_fulltime, "Any", "Tunisia", pref_types=["full-time"]) is True
    assert pipeline._passes(job_internship, "Any", "Tunisia", pref_types=["full-time"]) is False
    assert pipeline._passes(job_stage_french, "Any", "Tunisia", pref_types=["full-time"]) is False

    # When user prefers Internship only: full-time is rejected
    assert pipeline._passes(job_fulltime, "Any", "Tunisia", pref_types=["internship"]) is False
    assert pipeline._passes(job_internship, "Any", "Tunisia", pref_types=["internship"]) is True
    assert pipeline._passes(job_stage_french, "Any", "Tunisia", pref_types=["internship"]) is True


def test_workspace_scoping_strictly_inside_root(tmp_path):
    # Setup dummy workspace
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    resumes_dir = ws_dir / "resumes"
    resumes_dir.mkdir()

    # Resume inside workspace
    valid_pdf = resumes_dir / "my_resume.pdf"
    valid_pdf.write_bytes(b"%PDF-1.4 dummy content")

    # File outside workspace
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_pdf = outside_dir / "secret_resume.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4 secret content")

    found = workspace.discover_resumes(ws_dir)
    paths = [f["path"] for f in found]
    assert str(valid_pdf.resolve()) in paths
    assert str(outside_pdf.resolve()) not in paths

