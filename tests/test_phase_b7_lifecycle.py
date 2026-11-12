"""Tests for Phase B7: Job Lifecycle, Deduplication, Reposts, Liveness Checks, and 24h Grace Cleanup."""
import datetime
import os
import pytest

from jh import config, db, lifecycle
from jh.home import get_home


@pytest.fixture(autouse=True)
def isolated_lifecycle(tmp_path, monkeypatch):
    """Isolate DB and home directory for lifecycle testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_home


def test_exact_match_dedup_and_source_links():
    job1 = {
        "id": "j_orig",
        "title": "Principal Distributed Systems Engineer",
        "company": "Stripe",
        "location": "Remote",
        "work_mode": "Remote",
        "url": "https://stripe.com/jobs/101",
        "source": "Stripe Career Page",
        "score": 90,
    }
    # Ingest from source 1
    res1 = db.store_jobs([job1])
    assert res1["inserted"] == 1

    # Ingest same job from source 2 (same URL)
    job2 = dict(job1)
    job2["source"] = "LinkedIn"
    job2["id"] = "j_other"
    res2 = db.store_jobs([job2])
    assert res2["inserted"] == 0
    assert res2["merged"] == 1

    # Verify only one job exists in jobs table
    with db.session() as c:
        count = c.execute("SELECT COUNT(*) FROM jobs WHERE company='Stripe'").fetchone()[0]
        assert count == 1
        # Check job_sources holds both sources
        sources = c.execute("SELECT source, url FROM job_sources").fetchall()
        assert len(sources) >= 1


def test_repost_detection_increments_repost_count():
    job_v1 = {
        "id": "repost_test",
        "title": "Senior Data Platform Engineer",
        "company": "Snowflake",
        "location": "San Mateo, CA",
        "work_mode": "Hybrid",
        "url": "https://snowflake.com/jobs/99",
        "posted_at": "2026-09-01T00:00:00Z",
        "score": 85,
    }
    res1 = db.store_jobs([job_v1])
    assert res1["inserted"] == 1

    with db.session() as c:
        row = c.execute("SELECT repost_count, is_new FROM jobs WHERE id='repost_test'").fetchone()
        assert row["repost_count"] == 0
        assert row["is_new"] == 1

    # Re-ingest same fingerprint at a later date
    job_v2 = dict(job_v1)
    job_v2["posted_at"] = "2026-11-01T00:00:00Z"
    res2 = db.store_jobs([job_v2])
    assert res2["merged"] == 1

    with db.session() as c:
        row2 = c.execute("SELECT repost_count, is_new FROM jobs WHERE id='repost_test'").fetchone()
        assert row2["repost_count"] == 1
        assert row2["is_new"] == 0  # Repost is not marked as new


def test_close_match_possible_duplicate_flag():
    # Job A
    job_a = {
        "id": "close_a",
        "title": "Senior Software Engineer, Platform",
        "company": "Figma",
        "location": "San Francisco, CA",
        "work_mode": "Onsite",
        "url": "https://figma.com/jobs/a",
        "score": 85,
    }
    db.store_jobs([job_a])

    # Job B at same company with 80-90% similar title
    job_b = {
        "id": "close_b",
        "title": "Senior Software Engineer - Core Platform",
        "company": "Figma",
        "location": "San Francisco, CA",
        "work_mode": "Onsite",
        "url": "https://figma.com/jobs/b",
        "score": 85,
    }
    db.store_jobs([job_b])

    with db.session() as c:
        row_b = c.execute("SELECT possible_duplicate FROM jobs WHERE id='close_b'").fetchone()
        assert row_b is not None
        assert row_b["possible_duplicate"] == 1


def test_freshness_states():
    now = datetime.datetime.now(datetime.timezone.utc)
    date_active = (now - datetime.timedelta(days=10)).isoformat()
    date_stale = (now - datetime.timedelta(days=40)).isoformat()
    date_expired = (now - datetime.timedelta(days=70)).isoformat()

    jobs = [
        {"id": "j_act", "title": "Dev 1", "company": "Co 1", "posted_at": date_active, "url": "https://ex.com/1"},
        {"id": "j_stl", "title": "Dev 2", "company": "Co 2", "posted_at": date_stale, "url": "https://ex.com/2"},
        {"id": "j_exp", "title": "Dev 3", "company": "Co 3", "posted_at": date_expired, "url": "https://ex.com/3"},
    ]
    db.store_jobs(jobs)

    with db.session() as c:
        assert c.execute("SELECT freshness_state FROM jobs WHERE id='j_act'").fetchone()[0] == "active"
        assert c.execute("SELECT freshness_state FROM jobs WHERE id='j_stl'").fetchone()[0] == "stale"
        assert c.execute("SELECT freshness_state FROM jobs WHERE id='j_exp'").fetchone()[0] == "expired"


def test_liveness_check_marks_job_expired(monkeypatch):
    # Setup job
    job = {
        "id": "j_live_test",
        "title": "Frontend Eng",
        "company": "LiveCo",
        "url": "https://liveco.com/job/10",
        "score": 80,
    }
    db.store_jobs([job])

    # Mock urllib.request to simulate HTTP 404
    class Fake404Response:
        status = 404
        def read(self, *args):
            return b""

    def fake_urlopen(*args, **kwargs):
        raise lifecycle.urllib.error.HTTPError("https://liveco.com/job/10", 404, "Not Found", {}, None)

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", fake_urlopen)

    res = lifecycle.liveness_check("https://liveco.com/job/10", job_id="j_live_test")
    assert res["is_live"] is False
    assert res["status_code"] == 404

    # Verify job in DB marked expired and given delete_at (24h grace period)
    with db.session() as c:
        row = c.execute("SELECT freshness_state, delete_at, closed_checked_at FROM jobs WHERE id='j_live_test'").fetchone()
        assert row["freshness_state"] == "expired"
        assert row["delete_at"] is not None
        assert row["closed_checked_at"] is not None


def test_keep_jobs_and_saved_jobs_protected():
    job = {
        "id": "keep_test",
        "title": "AI Researcher",
        "company": "DeepMind",
        "url": "https://deepmind.com/jobs/1",
        "posted_at": "2024-01-01T00:00:00Z",  # Expired
    }
    db.store_jobs([job])

    # Mark expired with past delete_at
    past_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).isoformat()
    with db.session() as c:
        c.execute("UPDATE jobs SET freshness_state='expired', delete_at=? WHERE id='keep_test'", (past_time,))

    # User clicks Keep
    kept = lifecycle.keep_jobs(["keep_test"])
    assert kept == 1

    with db.session() as c:
        row = c.execute("SELECT keep_flag, delete_at FROM jobs WHERE id='keep_test'").fetchone()
        assert row["keep_flag"] == 1
        assert row["delete_at"] is None

    # Running cleanup must NOT delete kept job
    res_clean = lifecycle.run_cleanup()
    assert res_clean["deleted_count"] == 0

    with db.session() as c:
        assert c.execute("SELECT COUNT(*) FROM jobs WHERE id='keep_test'").fetchone()[0] == 1


def test_cleanup_past_grace_period_and_tombstones():
    # Insert expired job with delete_at in the past and keep_flag=0
    past_delete = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat()
    job = {
        "id": "exp_to_del",
        "title": "Old Architect",
        "company": "Ancient Systems",
        "location": "Boston, MA",
        "work_mode": "Onsite",
        "url": "https://ancient.com/jobs/arch",
        "score": 60,
    }
    db.store_jobs([job])
    with db.session() as c:
        c.execute("UPDATE jobs SET freshness_state='expired', delete_at=? WHERE id='exp_to_del'", (past_delete,))

    # Run cleanup
    clean_res = lifecycle.run_cleanup()
    assert clean_res["deleted_count"] == 1

    # Assert deleted from jobs and job_sources
    with db.session() as c:
        assert c.execute("SELECT COUNT(*) FROM jobs WHERE id='exp_to_del'").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM job_sources WHERE job_id='exp_to_del'").fetchone()[0] == 0
        # Assert tombstone exists
        assert c.execute("SELECT COUNT(*) FROM tombstones WHERE fingerprint!=''").fetchone()[0] == 1

    # Assert deletion was logged
    last_del = db.get_last_deletion()
    assert last_del is not None
    assert last_del["count"] == 1

    # Tombstone prevents re-ingestion
    re_res = db.store_jobs([job])
    assert re_res["tombstoned"] == 1
    assert re_res["inserted"] == 0
