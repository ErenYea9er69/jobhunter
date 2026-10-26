"""Unit tests for ResumeRegistry per Section 6.2 of newall-logic.md."""
import json
import pytest
from pathlib import Path
from jh.resume_registry import ResumeRegistry


@pytest.fixture
def test_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    resumes_dir = ws / "resumes"
    resumes_dir.mkdir()

    # Create dummy text resumes
    backend = resumes_dir / "backend_dev.txt"
    backend.write_text("Senior Backend Engineer\nSkills: Python, Go, PostgreSQL.\nExperience: Led distributed systems at CloudCorp.\nEmail: backend@test.com")

    frontend = ws / "frontend_resume.txt"
    frontend.write_text("Frontend Developer\nSkills: React, TypeScript, CSS.\nExperience: Built modern web apps at DesignCorp.\nEmail: frontend@test.com")

    return ws


def test_resume_registry_initial_scan(test_workspace):
    reg = ResumeRegistry(test_workspace)
    summary = reg.scan_and_sync(force=False)

    assert summary["total_files"] == 2
    assert summary["parsed_count"] == 2
    assert summary["cached_count"] == 0

    variants = reg.list_variants()
    assert len(variants) == 2
    names = {v["name"].lower() for v in variants}
    assert "backend dev" in names or "backend_dev" in names
    assert reg.get_active_variant() is not None


def test_resume_registry_incremental_skip(test_workspace):
    reg = ResumeRegistry(test_workspace)
    first_summary = reg.scan_and_sync(force=False)
    assert first_summary["parsed_count"] == 2

    # Second scan without changes: should use cache
    second_summary = reg.scan_and_sync(force=False)
    assert second_summary["total_files"] == 2
    assert second_summary["parsed_count"] == 0
    assert second_summary["cached_count"] == 2


def test_resume_registry_force_reparse(test_workspace):
    reg = ResumeRegistry(test_workspace)
    reg.scan_and_sync(force=False)

    forced_summary = reg.scan_and_sync(force=True)
    assert forced_summary["parsed_count"] == 2
    assert forced_summary["cached_count"] == 0


def test_resume_registry_file_modification(test_workspace):
    reg = ResumeRegistry(test_workspace)
    reg.scan_and_sync(force=False)

    # Modify one file
    backend = test_workspace / "resumes" / "backend_dev.txt"
    backend.write_text("Senior Staff Backend Engineer with Python, Rust, and Kubernetes.")

    mod_summary = reg.scan_and_sync(force=False)
    assert mod_summary["parsed_count"] == 1
    assert mod_summary["cached_count"] == 1


def test_resume_registry_active_variant_switch(test_workspace):
    reg = ResumeRegistry(test_workspace)
    reg.scan_and_sync()

    variants = reg.list_variants()
    target_name = variants[0]["name"]
    success = reg.set_active_variant(target_name)
    assert success is True
    assert reg.get_active_variant() == target_name
