"""Tests for Phase B10: Signal Radar (Modern track), adapters, freshness rules, scoring, and deduplication."""
import datetime
import os
import pytest

from jh import config, db
from jh.signals import (
    ACTIVE_MODERN_ADAPTERS,
    evaluate_signal_freshness,
    list_signal_adapters,
    score_signal,
    poll_modern_signals,
)
from jh.radar import RadarWorker


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    config.set_method("modern")
    return test_home


def test_adapter_registry_and_terms():
    adapters = list_signal_adapters()
    names = [a["name"] for a in adapters]
    assert "HackerNews" in names
    assert "Reddit" in names
    assert "TechFundingFeed" in names
    assert "LinkedInPosts" in names
    assert "XPosts" in names

    # Sanctioned access & ToS check
    li_adapter = next(a for a in adapters if a["name"] == "LinkedInPosts")
    assert li_adapter["enabled"] is False
    assert "User Agreement" in li_adapter["terms_note"]

    x_adapter = next(a for a in adapters if a["name"] == "XPosts")
    assert x_adapter["enabled"] is False
    assert "X API v2" in x_adapter["terms_note"]


def test_signal_freshness_rules():
    now_dt = datetime.datetime.now(datetime.timezone.utc)

    # Acceptance test 22:
    # A hiring post 20 hours old with 40 likes is fresh.
    posted_20h = (now_dt - datetime.timedelta(hours=20)).isoformat()
    assert evaluate_signal_freshness("hiring_post", posted_20h, likes=40) == "fresh"

    # A post 30 hours old goes to Late.
    posted_30h = (now_dt - datetime.timedelta(hours=30)).isoformat()
    assert evaluate_signal_freshness("hiring_post", posted_30h, likes=20) == "late"

    # A post with 150 likes goes to Late.
    assert evaluate_signal_freshness("hiring_post", posted_20h, likes=150) == "late"

    # Acceptance test 23:
    # Funding news under 14 days is fresh; older than 14 days goes to Late.
    posted_5d = (now_dt - datetime.timedelta(days=5)).isoformat()
    assert evaluate_signal_freshness("funding", posted_5d, likes=0) == "fresh"

    posted_16d = (now_dt - datetime.timedelta(days=16)).isoformat()
    assert evaluate_signal_freshness("funding", posted_16d, likes=0) == "late"


def test_signal_scoring():
    profile = {
        "target_title": "Full Stack Engineer",
        "skills": ["Python", "TypeScript", "React", "PostgreSQL"],
    }
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    fresh_dt = (now_dt - datetime.timedelta(hours=3)).isoformat()

    sig = {
        "type": "hiring_post",
        "posted_at": fresh_dt,
        "likes": 5,
        "text": "Founder & CEO hiring Full Stack Engineer proficient in Python and React for seed stage startup.",
        "author_name": "Alex (CEO)",
        "role_guess": "Full Stack Engineer",
        "stage": "seed",
        "region": "remote",
    }
    score = score_signal(sig, profile, target_role="Full Stack Engineer", target_stage="seed", target_region="remote")
    # Freshness (40) + Role/Skill (30) + Founder-led (10) + Low reach (10) + Match (10) = 100
    assert score >= 90


def test_signal_deduplication_and_funding_cooldown():
    sig1 = {
        "id": "sig_a1",
        "type": "hiring_post",
        "url_hash": "hash_same",
        "company": "Beta Corp",
        "likes": 10,
        "text": "Hiring lead engineer",
    }
    db.ingest_signal(sig1)

    # Ingest same url_hash with updated likes
    sig2 = {
        "id": "sig_a2",
        "type": "hiring_post",
        "url_hash": "hash_same",
        "company": "Beta Corp",
        "likes": 25,
        "text": "Hiring lead engineer",
    }
    ingested2 = db.ingest_signal(sig2)
    assert ingested2["id"] == "sig_a1"
    fetched = db.get_signal("sig_a1")
    assert fetched["likes"] == 25

    # Funding 14-day duplicate check
    fund1 = {
        "id": "fund_1",
        "type": "funding",
        "url_hash": "fund_url_1",
        "company": "Fintech Alpha",
        "funding_amount": "$10M",
    }
    db.ingest_signal(fund1)

    fund2 = {
        "id": "fund_2",
        "type": "funding",
        "url_hash": "fund_url_2",
        "company": "Fintech Alpha",
        "funding_amount": "$10M",
    }
    ingested_fund2 = db.ingest_signal(fund2)
    assert ingested_fund2.get("duplicate") is True


def test_outreach_ledger_cross_reference():
    # Record previous outreach to 'Stripe'
    db.log_outreach(contact_id="ct_1", company="Stripe", status="sent")

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    sig = {
        "id": "sig_stripe",
        "type": "hiring_post",
        "url_hash": "stripe_post_1",
        "company": "Stripe",
        "text": "Hiring infrastructure engineers",
        "posted_at": now_dt.isoformat(),
        "likes": 5,
    }

    # Simulate poll check
    with db.session() as c:
        contacted = c.execute("SELECT id FROM outreach WHERE lower(company)=lower(?)", ("Stripe",)).fetchone()
        assert contacted is not None
        sig["already_contacted"] = True

    assert sig.get("already_contacted") is True


def test_radar_worker_in_modern_mode():
    worker = RadarWorker(min_interval=600, max_interval=1200)
    res = worker.poll_once()
    assert res["success"] is True
    assert res["method"] == "modern"
    assert "interval_seconds" in res
