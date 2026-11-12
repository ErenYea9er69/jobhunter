"""Tests for Phase B6: Refresh scheduler for non-LinkedIn sources with adaptive TTL and 15m cooldown."""
import datetime
import os
import pytest

from jh import config, db, refresh_scheduler
from jh.home import get_home


@pytest.fixture(autouse=True)
def isolated_refresh(tmp_path, monkeypatch):
    """Isolate DB and home directory for refresh testing."""
    test_home = tmp_path / "jobmcp_test"
    monkeypatch.setenv("JOBMCP_HOME", str(test_home))
    test_db = test_home / "data" / "engine.db"
    monkeypatch.setattr(config, "DATA_DIR", str(test_home / "data"))
    monkeypatch.setattr(config, "DB_PATH", str(test_db))
    os.makedirs(test_home / "data", exist_ok=True)
    db.init_db()
    return test_home


def test_adaptive_ttl_formula():
    base = 43200  # 12 hours

    # 1. High yield (> 20% new): cuts TTL in half (x0.5), floor 6 hours (21600)
    ttl_high = refresh_scheduler.compute_new_ttl(base, 0.25)
    assert ttl_high == 21600  # 43200 * 0.5 = 21600

    # Even higher yield respects 6h floor
    ttl_floor = refresh_scheduler.compute_new_ttl(21600, 0.50)
    assert ttl_floor == 21600

    # 2. Low yield (< 5% new): increases TTL by 1.5 (x1.5), ceiling 48 hours (172800)
    ttl_low = refresh_scheduler.compute_new_ttl(base, 0.02)
    assert ttl_low == int(43200 * 1.5)  # 64800

    # Large TTL respects 48h ceiling
    ttl_ceiling = refresh_scheduler.compute_new_ttl(160000, 0.01)
    assert ttl_ceiling == 172800

    # 3. Normal yield (5% to 20% new): TTL unchanged
    ttl_mid = refresh_scheduler.compute_new_ttl(base, 0.12)
    assert ttl_mid == base


def test_cooldown_enforcement():
    iso_now = db.now_iso()
    # Mark Greenhouse as run 5 minutes ago
    recent_run = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
    db.update_refresh_state("Greenhouse", last_run_at=recent_run, ttl_seconds=43200)

    # Attempt to force refresh Greenhouse
    res = refresh_scheduler.run_refresh(source="Greenhouse", force=True)
    assert len(res["ran"]) == 0
    assert len(res["skipped"]) == 1
    assert res["skipped"][0]["reason"] == "cooldown"
    assert res["skipped"][0]["cooldown_remaining_seconds"] > 0


def test_not_due_sources_fresh_message():
    # Mark all sources as having run 30 minutes ago with 12h TTL
    recent_run = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)).isoformat()
    for s in refresh_scheduler.NON_RADAR_SOURCES:
        db.update_refresh_state(s, last_run_at=recent_run, ttl_seconds=43200)

    # Without force, none should be due
    res = refresh_scheduler.run_refresh(force=False)
    assert res["status"] == "fresh"
    assert "Sources are fresh" in res["message"]
    assert res["min_remaining_seconds"] > 0


def test_partial_failure_resilience():
    # Mock scraper_fn where Greenhouse succeeds with 30% new jobs and Lever throws an exception
    def mock_scraper(source_name):
        if source_name == "Greenhouse":
            return [
                {
                    "id": f"gh_job_{i}",
                    "title": f"DevOps {i}",
                    "company": "GitLab",
                    "location": "Remote",
                    "work_mode": "Remote",
                    "url": f"https://example.com/gh/{i}",
                    "score": 85,
                }
                for i in range(10)
            ]
        elif source_name == "Lever":
            raise RuntimeError("HTTP 503 Service Unavailable: Lever upstream down")
        return []

    # Run refresh for Greenhouse and Lever
    # First ensure neither is in cooldown
    old_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=20)).isoformat()
    db.update_refresh_state("Greenhouse", last_run_at=old_time, ttl_seconds=43200)
    db.update_refresh_state("Lever", last_run_at=old_time, ttl_seconds=43200)

    res = refresh_scheduler.run_refresh(source=None, force=True, scraper_fn=mock_scraper)
    assert res["status"] == "ok"

    gh_res = next((r for r in res["ran"] if r["source"] == "Greenhouse"), None)
    assert gh_res is not None
    assert gh_res["status"] == "success"
    assert gh_res["new_ttl"] == 21600  # High yield (10 new jobs out of 10 = 100%) cuts TTL to 6h

    lever_res = next((r for r in res["ran"] if r["source"] == "Lever"), None)
    assert lever_res is not None
    assert lever_res["status"] == "error"
    assert "503" in lever_res["error"]
    assert lever_res["ttl_seconds"] == 43200  # TTL unchanged on failure


def test_get_all_refresh_status():
    status = refresh_scheduler.get_all_refresh_status()
    assert len(status["sources"]) == len(refresh_scheduler.NON_RADAR_SOURCES)
    assert any(s["source"] == "Greenhouse" for s in status["sources"])
