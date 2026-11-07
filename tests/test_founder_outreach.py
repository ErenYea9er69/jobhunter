"""Tests for startup founder cold outreach engine."""

import pytest
from jh import db, founder_outreach


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    monkeypatch.setattr("jh.config.DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_generate_founder_cold_email_scale_velocity():
    profile = {
        "name": "Alex Hunter",
        "target_title": "Full Stack Engineer",
        "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "experience": [
            {
                "company": "FastTech",
                "role": "Software Engineer",
                "bullets": ["Scaled FastAPI microservices handling 4M requests/day and cut latency by 35%."],
            }
        ],
        "email": "alex@example.com",
        "github": "github.com/alexhunter",
    }
    job = {
        "company": "Vercel",
        "title": "Backend Infrastructure Engineer",
        "description": "Looking for a Python and FastAPI engineer to build high throughput systems.",
    }

    res = founder_outreach.generate_founder_cold_email(
        job,
        profile,
        founder_name="Guillermo",
        founder_role="CEO",
        angle="scale_velocity",
    )

    assert res["company"] == "Vercel"
    assert res["founder_name"] == "Guillermo"
    assert len(res["subject_options"]) == 3
    assert "Hi Guillermo," in res["body"]
    assert "Vercel" in res["body"]
    assert "FastAPI" in res["body"] or "Python" in res["body"]
    assert res["word_count"] < 130
    assert "Bumping this to the top of your inbox" in res["follow_up_note"]
    assert "mail.google.com" in res["gmail_compose_url"]
    assert res["review"]["verdict"].lower() in ("pass", "warn")


def test_generate_founder_cold_email_product_teardown():
    profile = {
        "name": "Sarah Connor",
        "target_title": "Senior Backend Developer",
        "skills": ["Go", "Kubernetes", "PostgreSQL"],
        "experience": [
            {
                "company": "CloudScale",
                "role": "Backend Engineer",
                "bullets": ["Architected distributed caching layers reducing DB load by 50%."],
            }
        ],
    }
    job = {
        "company": "Supabase",
        "title": "Database Engineer",
        "description": "Building real-time Postgres tooling with Go and Kubernetes.",
    }

    res = founder_outreach.generate_founder_cold_email(
        job,
        profile,
        founder_name="Paul",
        angle="product_teardown",
        custom_observation="your connection pooling architecture under heavy writes",
        recipient_email="paul@supabase.com",
    )

    assert "your connection pooling architecture under heavy writes" in res["body"]
    assert "paul@supabase.com" in res["gmail_compose_url"]
    assert res["word_count"] < 130


def test_gmail_draft_and_send_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setattr("jh.gmail_tracker.get_config_path", lambda: tmp_path / "unconfigured.json")
    draft_res = founder_outreach.save_draft_to_gmail("founder@startup.io", "Quick note", "Hello")
    assert draft_res["success"] is False
    assert draft_res["reason"] == "not_configured"

    send_res = founder_outreach.send_cold_email("founder@startup.io", "Quick note", "Hello")
    assert send_res["success"] is False
    assert send_res["reason"] == "not_configured"
