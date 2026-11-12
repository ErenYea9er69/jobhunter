"""Tests for Phase B5: Always-on LinkedIn Radar worker, lock management, and REST endpoints."""
import os
import time
import pytest

from jh import config, db, httpd, radar
from jh.home import get_home


@pytest.fixture(autouse=True)
def isolated_radar(tmp_path, monkeypatch):
    """Isolate DB and home directory for radar testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    os.makedirs(test_home / "run", exist_ok=True)
    db.init_db()
    yield test_home
    radar.stop_radar_worker()
    radar.release_radar_lock()


def test_radar_lock_and_pid_file():
    # 1. Acquire lock
    assert radar.acquire_radar_lock() is True
    pid_file = get_home() / "run" / "radar.pid"
    assert pid_file.is_file()
    assert int(pid_file.read_text().strip()) == os.getpid()

    # 2. Duplicate lock from same process returns True
    assert radar.acquire_radar_lock() is True

    # 3. Release lock
    radar.release_radar_lock()
    assert not pid_file.is_file()


def test_radar_poll_success_and_filter_matching(monkeypatch):
    # Setup view filters targeting 'backend'
    db.save_view_filters({"job_style": "backend", "roles": ["backend"]})

    # Mock pipeline.run_linkedin_incremental to stage 2 jobs
    def fake_incremental():
        staged_jobs = [
            {
                "id": "li_job_1",
                "title": "Staff Backend Engineer",
                "company": "LinkedInCo",
                "location": "Remote",
                "work_mode": "Remote",
                "url": "https://www.linkedin.com/jobs/view/999001",
                "source": "LinkedIn",
                "score": 90,
            },
            {
                "id": "li_job_2",
                "title": "Marketing Manager",
                "company": "GrowthCo",
                "location": "Onsite",
                "work_mode": "Onsite",
                "url": "https://www.linkedin.com/jobs/view/999002",
                "source": "LinkedIn",
                "score": 60,
            }
        ]
        with db.session() as c:
            for j in staged_jobs:
                c.execute("""
                    INSERT OR REPLACE INTO pending_search_jobs (job_key, query, title, company, location, work_mode, job_json, discovered_at)
                    VALUES (?, 'linkedin', ?, ?, ?, ?, ?, ?)
                """, (j["id"], j["title"], j["company"], j["location"], j["work_mode"], db.json.dumps(j), db.now_iso()))
        return len(staged_jobs)

    monkeypatch.setattr(radar.pipeline, "run_linkedin_incremental", fake_incremental)

    worker = radar.RadarWorker(min_interval=600, max_interval=1200)
    res = worker.poll_once()

    assert res["success"] is True
    assert res["discovered"] == 2
    assert res["new_ingested"] == 2
    assert res["matching_filters"] == 1  # only Staff Backend Engineer matches

    # Event must be triggered
    evt = radar.get_latest_event()
    assert evt is not None
    assert evt["new_matching_filters"] == 1
    assert "Staff Backend Engineer" in evt["top_titles"]

    # Verify jobs table has is_new=1, seen_by_user=0
    with db.session() as c:
        row = c.execute("SELECT is_new, seen_by_user FROM jobs WHERE id='li_job_1'").fetchone()
        assert row["is_new"] == 1
        assert row["seen_by_user"] == 0

    # Verify radar_state in DB updated
    r_state = db.get_radar_state()
    assert r_state["status"] == "idle"
    assert r_state["failure_count"] == 0
    assert r_state["last_poll_at"] is not None


def test_radar_backoff_and_warning_status(monkeypatch):
    # Mock pipeline.run_linkedin_incremental to raise 429 error
    def fail_incremental():
        raise RuntimeError("HTTP 429 Too Many Requests: Rate limit exceeded")

    monkeypatch.setattr(radar.pipeline, "run_linkedin_incremental", fail_incremental)

    worker = radar.RadarWorker(min_interval=600, max_interval=1200)
    worker.current_interval = 600

    # Failure 1: backoff doubles interval
    f1 = worker.poll_once()
    assert f1["success"] is False
    assert f1["failure_count"] == 1
    assert f1["status"] == "idle"
    assert worker.current_interval == 1200

    # Failure 2
    f2 = worker.poll_once()
    assert f2["failure_count"] == 2
    assert worker.current_interval == 2400

    # Failure 3: triggers 'warning' status
    f3 = worker.poll_once()
    assert f3["failure_count"] == 3
    assert f3["status"] == "warning"
    assert worker.current_interval == 4800

    r_db = db.get_radar_state()
    assert r_db["status"] == "warning"
    assert "429" in r_db["last_error"]


def test_radar_ack_jobs():
    # Insert new job
    db.store_jobs([{
        "id": "ack_test_1",
        "title": "Backend Dev",
        "company": "AckCo",
        "location": "Remote",
        "work_mode": "Remote",
        "url": "https://example.com/ack1",
        "score": 80,
    }])
    with db.session() as c:
        unread = c.execute("SELECT COUNT(*) FROM jobs WHERE is_new=1").fetchone()[0]
        assert unread == 1

    # Acknowledge jobs
    affected = radar.ack_radar_jobs()
    assert affected >= 1

    with db.session() as c:
        unread_after = c.execute("SELECT COUNT(*) FROM jobs WHERE is_new=1").fetchone()[0]
        assert unread_after == 0
