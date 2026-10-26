"""Unit tests for 5-stage duplicate resolution and 100-point explainable fit scoring per Sections 9.1 & 10 of newall-logic.md."""
import pytest
from jh.dedup import resolve_duplicates_5stage
from jh.scoring import calculate_explainable_fit


def test_dedup_provider_identity_stage_1():
    # Same provider and job ID
    post1 = {
        "id": "gh-999",
        "title": "Software Engineer",
        "company": "Figma",
        "source": "Greenhouse",
        "url": "https://boards.greenhouse.io/figma/jobs/999",
        "apply_url": "https://figma.com/apply/999"
    }
    post2 = {
        "id": "gh-999",
        "title": "Software Engineer (Backend)",
        "company": "Figma",
        "source": "Greenhouse",
        "url": "https://boards.greenhouse.io/figma/jobs/999?gh_src=feed",
        "apply_url": "https://figma.com/apply/999"
    }
    merged, uncertain = resolve_duplicates_5stage([post1, post2])
    assert len(merged) == 1
    assert len(uncertain) == 0
    # Retains source occurrences
    assert len(merged[0]["sources"]) == 2


def test_dedup_canonical_url_preserves_apply_url_stage_2():
    post1 = {
        "id": "j1",
        "title": "Go Developer",
        "company": "Datadog",
        "source": "Jobicy",
        "url": "https://datadog.com/careers/123?utm_source=jobicy",
        "apply_url": "https://jobicy.com/apply/datadog-123"
    }
    post2 = {
        "id": "j2",
        "title": "Go Developer",
        "company": "Datadog",
        "source": "Himalayas",
        "url": "https://datadog.com/careers/123",
        "apply_url": "https://himalayas.app/apply/datadog-123"
    }
    merged, _ = resolve_duplicates_5stage([post1, post2])
    assert len(merged) == 1
    # Both apply URLs must be preserved in source records
    apply_links = {s["apply_url"] for s in merged[0]["sources"]}
    assert "https://jobicy.com/apply/datadog-123" in apply_links
    assert "https://himalayas.app/apply/datadog-123" in apply_links


def test_dedup_distinct_openings_not_collapsed():
    post1 = {
        "id": "eng-1",
        "title": "Backend Engineer - Platform",
        "company": "Uber",
        "location": "San Francisco",
        "url": "https://uber.com/jobs/1"
    }
    post2 = {
        "id": "eng-2",
        "title": "Frontend Engineer - Mobile Web",
        "company": "Uber",
        "location": "New York",
        "url": "https://uber.com/jobs/2"
    }
    merged, _ = resolve_duplicates_5stage([post1, post2])
    assert len(merged) == 2


def test_explainable_fit_score_weights_and_normalization():
    profile = {
        "name": "Jane Developer",
        "skills": ["Python", "PostgreSQL", "Docker", "FastAPI"],
        "years_of_experience": 6.0,
        "work_mode_preference": "Remote",
    }
    job = {
        "title": "Senior Python Backend Engineer",
        "company": "TechCorp",
        "description": "Looking for Senior Engineer with Python, FastAPI, and PostgreSQL. Remote.",
        "work_mode": "Remote",
        "location": "Remote",
        "salary": "",  # missing salary should NOT cause zero score or penalty
    }

    res = calculate_explainable_fit(profile, job)
    assert 0 <= res["fit_score"] <= 100
    assert "breakdown" in res
    bd = res["breakdown"]
    # Check 6 dimensions
    assert "skills" in bd
    assert "responsibilities" in bd
    assert "seniority" in bd
    assert "domain" in bd
    assert "work_conditions" in bd
    assert "compensation" in bd

    assert res["score_confidence"] in ("high", "medium", "low")
    assert "eligibility" in res
    assert res["eligibility"] in ("met", "not_met", "unknown")


def test_eligibility_hard_constraints_separate_from_score():
    profile = {
        "skills": ["Python", "Django"],
        "work_mode_preference": "Remote",
    }
    # On-site role in London when user requested Remote
    job = {
        "title": "Python Developer",
        "work_mode": "On-site",
        "location": "London, UK",
        "description": "Must work 5 days in London office.",
    }
    res = calculate_explainable_fit(profile, job)
    # Fit score still evaluates skills/domain, but eligibility is not_met
    assert res["eligibility"] == "not_met"
    assert res["eligibility_details"]["work_mode"] == "not_met"
