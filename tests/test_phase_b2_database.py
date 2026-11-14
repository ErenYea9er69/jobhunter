"""Tests for Phase B2: Database schema, migrations, and lifecycle tracking."""
import os
import sqlite3
import pytest

from jh import config, db, dedup
from jh.home import get_home


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isolate DB to a temporary folder for testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_db


def test_schema_version_and_tables(isolated_db):
    with db.session() as c:
        row = c.execute("PRAGMA user_version").fetchone()
        assert row[0] >= 5

        # Check required tables exist
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        required = {
            "session_state",
            "profile",
            "view_filters",
            "jobs",
            "job_sources",
            "tombstones",
            "deletions_log",
            "radar_state",
            "refresh_state",
            "dismissals",
            "applications",
            "signals",
            "company_briefs",
            "contacts",
            "outreach",
        }
        assert required.issubset(tables)

        # Check default settings
        assert db.get_setting("cleanup_grace_hours") == "24"
        assert db.get_setting("method") == "modern"
        assert db.get_setting("daily_cap") == "20"
        assert db.get_setting("follow_up_days") == "4"
        assert db.get_setting("first_touch_attachment") == "1"
        assert db.get_setting("send_mode") == "one_at_a_time"
        assert db.get_setting("resume_max_kb") == "200"


def test_session_state_helpers():
    state = db.get_session_state()
    assert state["current_state"] == "idle"

    updated = db.set_session_state("searching", "jh_search")
    assert updated["current_state"] == "searching"
    assert updated["last_tool"] == "jh_search"

    # Updating state without tool preserves last_tool
    updated2 = db.set_session_state("viewing")
    assert updated2["current_state"] == "viewing"
    assert updated2["last_tool"] == "jh_search"


def test_profile_columns_and_save():
    p = db.get_profile()
    assert "_profile_id" in p

    db.save_profile({
        "target_title": "Senior Staff Engineer",
        "target_roles": ["Software Architect", "Staff Engineer"],
        "skills": ["Python", "Rust", "Distributed Systems"],
        "years_of_experience": 10.5,
        "resume_path": "/tmp/resume.pdf",
        "portfolio_url": "https://github.com/myuser/portfolio",
        "proof_points": [
            {"project": "Distributed DB", "metric": "Reduced p99 latency by 45%", "link": "https://github.com/myuser/db"}
        ],
    }, profile_id="master")

    with db.session() as c:
        row = c.execute("SELECT roles, years, skills, resume_path, portfolio_url, proof_points FROM profile WHERE id=1").fetchone()
        assert row is not None
        assert "Software Architect" in row["roles"]
        assert row["years"] == 10.5
        assert "Python" in row["skills"]
        assert row["resume_path"] == "/tmp/resume.pdf"
        assert row["portfolio_url"] == "https://github.com/myuser/portfolio"
        assert "Distributed DB" in row["proof_points"]


def test_view_filters_crud():
    defaults = db.get_view_filters("session_1")
    assert defaults["job_style"] == ""
    assert defaults["work_mode"] == "any"
    assert defaults["posting_age"] == 30
    assert defaults["show_unknown_salary"] is True

    saved = db.save_view_filters({
        "job_style": "backend systems",
        "roles": ["Backend Engineer", "Platform Engineer"],
        "work_mode": "remote",
        "locations": ["US", "Canada"],
        "relocation": True,
        "visa_need": True,
        "visa_countries": ["US"],
        "min_salary": 160000,
        "currency": "USD",
        "period": "year",
        "contract_types": ["full-time"],
        "seniority": ["senior", "lead"],
        "company_sizes": ["enterprise", "startup"],
        "industries": ["cloud", "fintech"],
        "excluded_companies": ["RevSys"],
        "excluded_keywords": ["wordpress", "php"],
        "posting_age": 14,
        "show_unknown_salary": False,
    }, session_id="session_1")

    assert saved["job_style"] == "backend systems"
    assert "Platform Engineer" in saved["roles"]
    assert saved["work_mode"] == "remote"
    assert saved["relocation"] is True
    assert saved["visa_need"] is True
    assert saved["min_salary"] == 160000.0
    assert saved["show_unknown_salary"] is False

    # Fetch again
    fetched = db.get_view_filters("session_1")
    assert fetched["job_style"] == "backend systems"
    assert fetched["roles"] == ["Backend Engineer", "Platform Engineer"]
    assert fetched["excluded_companies"] == ["RevSys"]


def test_jobs_lifecycle_columns_and_sources():
    with db.session() as c:
        # Check jobs table columns
        cols = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        assert {
            "source", "url_hash", "fingerprint", "found_at", "first_seen_at",
            "last_seen_at", "is_new", "seen_by_user", "repost_count",
            "possible_duplicate", "freshness_state", "delete_at", "keep_flag",
            "closed_checked_at"
        }.issubset(cols)

        # Check job_sources schema and unique constraint
        c.execute("""
            INSERT INTO job_sources (job_id, source, url, url_hash, first_seen_at, last_seen_at)
            VALUES ('j1', 'LinkedIn', 'https://linkedin.com/jobs/view/12345', 'li:12345', '2026-11-12T00:00:00Z', '2026-11-12T00:00:00Z')
        """)
        # Duplicate url_hash should fail with IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("""
                INSERT INTO job_sources (job_id, source, url, url_hash, first_seen_at, last_seen_at)
                VALUES ('j2', 'LinkedIn', 'https://linkedin.com/jobs/view/12345', 'li:12345', '2026-11-12T01:00:00Z', '2026-11-12T01:00:00Z')
            """)


def test_tombstones_and_deletions():
    assert not db.is_tombstoned(url_hash="hash_abc", fingerprint="fp_xyz")
    db.add_tombstone("hash_abc", "fp_xyz")
    assert db.is_tombstoned(url_hash="hash_abc")
    assert db.is_tombstoned(fingerprint="fp_xyz")
    assert not db.is_tombstoned(url_hash="hash_other")

    db.log_deletion(5)
    last = db.get_last_deletion()
    assert last["count"] == 5
    assert last["acknowledged"] == 0

    status = db.get_cleanup_status()
    assert status["grace_hours"] == 24
    assert status["recently_deleted"] == 5
    assert status["tombstones_count"] >= 1

    db.ack_deletions()
    status2 = db.get_cleanup_status()
    assert status2["recently_deleted"] == 0


def test_radar_and_refresh_state():
    r_state = db.get_radar_state()
    assert r_state["status"] == "idle"

    updated_r = db.update_radar_state(status="working", failure_count=2, last_error="HTTP 429")
    assert updated_r["status"] == "working"
    assert updated_r["failure_count"] == 2
    assert updated_r["last_error"] == "HTTP 429"

    # Refresh state
    rf = db.get_refresh_state("builtin_greenhouse")
    assert rf["ttl_seconds"] == 43200
    db.update_refresh_state("builtin_greenhouse", last_total=50, last_new=10, last_new_ratio=0.2)
    rf2 = db.get_refresh_state("builtin_greenhouse")
    assert rf2["last_total"] == 50
    assert rf2["last_new"] == 10
    assert rf2["last_new_ratio"] == 0.2


def test_dismissals():
    assert db.count_dismissals() == 0
    db.add_dismissal("job_99", "Not relevant")
    assert db.count_dismissals() == 1
    d_list = db.get_dismissals("job_99")
    assert len(d_list) == 1
    assert d_list[0]["reason"] == "Not relevant"


def test_url_hash_and_fingerprint_builders():
    # LinkedIn job ID
    h1 = dedup.build_url_hash("https://www.linkedin.com/jobs/view/4102938475/?tracking=123")
    assert h1 == "li:4102938475"

    h2 = dedup.build_url_hash("https://www.linkedin.com/jobs/search/?currentJobId=4102938475&param=true")
    assert h2 == "li:4102938475"

    # Non-LinkedIn canonical URL hash
    h3 = dedup.build_url_hash("https://jobs.lever.co/stripe/abc-123?utm_source=board")
    h4 = dedup.build_url_hash("https://jobs.lever.co/stripe/abc-123/")
    assert h3 == h4
    assert len(h3) == 24

    # Fingerprint: lowercase company, title without seniority words/punct, city, work mode
    fp1 = dedup.build_fingerprint("Google, Inc.", "Senior Software Engineer (Backend)", "New York, NY", "remote")
    fp2 = dedup.build_fingerprint("google", "software engineer backend", "remote", "remote")
    assert fp1 == fp2

    # Title similarity
    sim = dedup.title_similarity("Senior Software Engineer", "Staff Software Engineer")
    assert sim == 1.0  # Seniority stripped

    sim2 = dedup.title_similarity("Frontend Developer", "Data Scientist")
    assert sim2 < 0.3


def test_signals_db_helpers():
    sig = {
        "id": "sig_test1",
        "type": "hiring_post",
        "source": "HN",
        "url": "https://news.ycombinator.com/item?id=123",
        "url_hash": "hn:123",
        "author_name": "sam_alt",
        "company": "Acme AI",
        "company_domain": "acme.ai",
        "text": "We are hiring founding ML engineers.",
        "posted_at": "2026-11-14T10:00:00Z",
        "likes": 12,
        "score": 85,
        "role_guess": "ML Engineer",
        "stage": "seed",
        "region": "remote",
    }
    ingested = db.ingest_signal(sig)
    assert ingested["id"] == "sig_test1"

    # Fetch signals
    sigs = db.get_signals(limit=10)
    assert len(sigs) >= 1
    assert sigs[0]["company"] == "Acme AI"

    # View filters matching
    matches = db.get_signals(view_filters={"role": "ML Engineer", "region": "remote"})
    assert len(matches) >= 1
    non_matches = db.get_signals(view_filters={"role": "Accountant"})
    assert len(non_matches) == 0

    # New signals count and ack
    count = db.get_new_signals_count()
    assert count >= 1
    acked = db.ack_signals(["sig_test1"])
    assert acked == 1
    assert db.get_new_signals_count() == 0

    # Status update
    db.update_signal_status("sig_test1", "saved")
    updated_sig = db.get_signal("sig_test1")
    assert updated_sig["status"] == "saved"


def test_company_briefs_and_contacts_db_helpers():
    brief_data = {
        "company": "Acme AI",
        "summary": "Building next-gen AI search",
        "stage": "Seed",
        "funding": "$5M led by Founders Fund",
        "team": "12 people",
    }
    lp_data = {
        "questions": ["How do you scale indexes?", "What is the GPU stack?"],
        "talking_points": ["Reduced latency by 45% on vector lookups"],
    }
    saved_b = db.save_company_brief("Acme AI", brief_data, lp_data, signal_id="sig_test1")
    assert saved_b["id"].startswith("brief_")

    fetched_b = db.get_company_brief("Acme AI")
    assert fetched_b is not None
    assert fetched_b["brief"]["summary"] == "Building next-gen AI search"

    # Contacts
    c1 = {
        "signal_id": "sig_test1",
        "company": "Acme AI",
        "name": "Jane Founder",
        "role": "Co-founder & CEO",
        "email": "jane@acme.ai",
        "confidence": "Found",
        "provider": "Hunter",
    }
    saved_c = db.save_contact(c1)
    assert saved_c["id"].startswith("ct_")

    contacts = db.get_contacts(company="Acme AI")
    assert len(contacts) >= 1
    assert contacts[0]["name"] == "Jane Founder"

    # Outreach
    out = db.log_outreach(contact_id=saved_c["id"], signal_id="sig_test1", company="Acme AI", status="draft")
    assert out["id"].startswith("out_")
    assert out["status"] == "draft"

    # Queue
    queue = db.get_outreach_queue()
    assert len(queue) >= 1

    # Mark sent
    sent = db.mark_outreach_sent(out["id"])
    assert sent["status"] == "sent"
    assert sent["follow_up_due"] is not None
    assert db.get_outreach_today_count() >= 1

    # Report
    rep = db.get_outreach_report()
    assert rep["total_sent"] >= 1
    assert "reply_rate" in rep

    # Delete contact
    deleted = db.delete_contact(saved_c["id"])
    assert deleted is True
    assert db.get_contact(saved_c["id"]) is None
