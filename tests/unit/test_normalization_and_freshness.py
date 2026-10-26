"""Unit tests for Canonical Job Normalization and Freshness lifecycle per Sections 8 & 9.2 of newall-logic.md."""
import pytest
from jh.normalization import build_canonical_posting, standardize_work_mode, standardize_employment_type
from jh.freshness import evaluate_freshness, FreshnessState


def test_standardize_work_mode():
    assert standardize_work_mode("100% remote anywhere") == "Remote"
    assert standardize_work_mode("Hybrid - 2 days office") == "Hybrid"
    assert standardize_work_mode("On-site in New York") == "On-site"
    assert standardize_work_mode("") == ""


def test_standardize_employment_type():
    assert standardize_employment_type("full_time") == "Full-time"
    assert standardize_employment_type("part-time contract") == "Contract"
    assert standardize_employment_type("internship") == "Internship"


def test_build_canonical_posting_separation_of_urls():
    raw = {
        "id": "gh-12345",
        "title": "Staff Backend Engineer",
        "company": "Stripe",
        "location": "San Francisco, CA",
        "description": "We are seeking a Staff Engineer with Go experience. Remote friendly.",
        "url": "https://boards.greenhouse.io/stripe/jobs/12345",
        "apply_url": "https://stripe.com/apply/12345?ref=jobhunter",
        "salary": "$200,000 - $250,000 USD",
        "job_type": "full-time",
        "posted_at": "2026-10-20T10:00:00Z"
    }

    canonical = build_canonical_posting(raw, source_name="Greenhouse")
    assert canonical["id"] == "gh-12345"
    assert canonical["title"] == "Staff Backend Engineer"
    assert canonical["company"] == "Stripe"
    assert canonical["source"] == "Greenhouse"
    assert canonical["source_url"] == "https://boards.greenhouse.io/stripe/jobs/12345"
    assert canonical["apply_url"] == "https://stripe.com/apply/12345?ref=jobhunter"
    assert canonical["work_mode"] in ("Remote", "Hybrid", "On-site")
    assert canonical["salary_currency"] == "USD"
    assert canonical["salary_min"] == 200000.0
    assert canonical["salary_max"] == 250000.0


def test_freshness_evaluation_states():
    # 1. Closed job
    closed_job = {"is_closed": True, "posted_at": "2026-10-20T00:00:00Z"}
    assert evaluate_freshness(closed_job) == FreshnessState.CLOSED

    # 2. Fresh open job
    recent_job = {"is_closed": False, "posted_at": "2026-10-25T00:00:00Z"}
    assert evaluate_freshness(recent_job, max_age_days=30) == FreshnessState.OPEN

    # 3. Stale job older than window
    old_job = {"is_closed": False, "posted_at": "2025-01-01T00:00:00Z"}
    assert evaluate_freshness(old_job, max_age_days=30) == FreshnessState.STALE

    # 4. Unknown when no dates and no verification
    empty_job = {}
    assert evaluate_freshness(empty_job) == FreshnessState.UNKNOWN
