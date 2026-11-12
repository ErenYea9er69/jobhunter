"""Tests for Phase B3: Broad search core, SQL view filters, soft ranking, and usable gates."""
import os
import pytest
from jh import config, db, dedup


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


def test_broad_storage_and_deduplication(isolated_db):
    sample_jobs = [
        {
            "id": "job1",
            "title": "Backend Software Engineer",
            "company": "Acme Corp",
            "location": "New York, NY",
            "work_mode": "Hybrid",
            "url": "https://example.com/jobs/1",
            "source": "Greenhouse",
            "min_salary": 140000,
            "max_salary": 180000,
            "score": 85,
            "opportunity_score": 90,
        },
        {
            "id": "job2",
            "title": "Frontend React Developer",
            "company": "Beta Tech",
            "location": "Remote",
            "work_mode": "Remote",
            "url": "https://example.com/jobs/2",
            "source": "Lever",
            "score": 80,
            "opportunity_score": 85,
        }
    ]

    res = db.store_jobs(sample_jobs, query="tech jobs")
    assert res["inserted"] == 2
    assert res["merged"] == 0

    # Ingesting the same job with same URL merges as repost
    dup_res = db.store_jobs([sample_jobs[0]], query="tech jobs")
    assert dup_res["inserted"] == 0
    assert dup_res["merged"] == 1

    # Verify repost count and is_new flag
    with db.session() as c:
        row = c.execute("SELECT repost_count, is_new FROM jobs WHERE company='Acme Corp'").fetchone()
        assert row["repost_count"] == 1
        assert row["is_new"] == 0


def test_query_jobs_hard_filters_and_soft_ranking(isolated_db):
    # Setup a realistic set of jobs
    jobs_data = [
        {
            "id": f"j_{i}",
            "title": "Senior Backend Engineer" if i % 2 == 0 else "Staff Frontend Engineer",
            "company": f"Company {i}",
            "location": "San Francisco, CA" if i % 3 == 0 else "Remote",
            "work_mode": "Remote" if i % 3 != 0 else "Onsite",
            "url": f"https://example.com/job/{i}",
            "source": "Greenhouse",
            "min_salary": 120000 + i * 5000,
            "max_salary": 150000 + i * 5000,
            "job_type": "full-time" if i % 4 != 0 else "contract",
            "seniority": "senior" if i % 2 == 0 else "staff",
            "industry": "Fintech" if i % 2 == 0 else "Healthcare",
            "company_size": "startup" if i % 2 == 0 else "enterprise",
            "score": 75 + i,
            "opportunity_score": 80 + i,
        }
        for i in range(15)
    ]
    db.store_jobs(jobs_data, query="tech")

    # 1. Filter by role='backend'
    q_backend = db.query_jobs({"roles": ["backend"]})
    assert all("backend" in j["title"].lower() for j in q_backend["jobs"])
    assert q_backend["removed_counts"]["roles"] > 0

    # 2. Filter by work_mode='remote'
    q_remote = db.query_jobs({"work_mode": "remote"})
    assert all("remote" in j["work_mode"].lower() or "remote" in j["location"].lower() for j in q_remote["jobs"])
    assert q_remote["removed_counts"]["work_mode"] > 0

    # 3. Filter by min_salary
    q_sal = db.query_jobs({"min_salary": 170000})
    assert all(j["max_salary"] >= 170000 for j in q_sal["jobs"])
    assert q_sal["removed_counts"]["salary"] > 0

    # 4. Soft preference ranking: boosting seniority 'staff' and company_size 'enterprise'
    q_ranked = db.query_jobs({
        "seniority": ["staff"],
        "company_sizes": ["enterprise"],
    })
    # Staff / Enterprise roles should receive boosts
    top_job = q_ranked["jobs"][0]
    assert top_job["rank_score"] > top_job["opportunity_score"]

    # 5. Filtering never deletes rows from DB
    with db.session() as c:
        total_in_db = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert total_in_db == 15


def test_query_jobs_unknown_salary_flag(isolated_db):
    jobs = [
        {
            "id": "sal_known",
            "title": "Software Engineer",
            "company": "KnownCo",
            "location": "Remote",
            "work_mode": "Remote",
            "url": "https://example.com/known",
            "min_salary": 150000,
            "max_salary": 180000,
            "score": 80,
        },
        {
            "id": "sal_unknown",
            "title": "Software Engineer",
            "company": "UnknownCo",
            "location": "Remote",
            "work_mode": "Remote",
            "url": "https://example.com/unknown",
            "score": 85,
        }
    ]
    db.store_jobs(jobs)

    # When show_unknown_salary is True (default), job with no salary stays visible with flag
    q_default = db.query_jobs({"min_salary": 140000, "show_unknown_salary": True})
    assert len(q_default["jobs"]) == 2
    u_job = next(j for j in q_default["jobs"] if j["company"] == "UnknownCo")
    assert u_job.get("unknown_salary") is True

    # When show_unknown_salary is False, job with no salary is hidden
    q_hidden = db.query_jobs({"min_salary": 140000, "show_unknown_salary": False})
    assert len(q_hidden["jobs"]) == 1
    assert q_hidden["jobs"][0]["company"] == "KnownCo"
    assert q_hidden["removed_counts"]["salary"] == 1


def test_query_jobs_closing_soon_and_usable_gate(isolated_db):
    # Add an expired job
    expired_job = {
        "id": "old_job",
        "title": "Legacy Cobol Dev",
        "company": "Old Bank",
        "location": "Remote",
        "url": "https://example.com/old",
        "posted_at": "2024-01-01T00:00:00Z",  # Well over 60 days
        "score": 50,
    }
    # Add 5 active jobs (too few for usable gate < 10)
    few_jobs = [
        {
            "id": f"active_{i}",
            "title": f"DevOps Engineer {i}",
            "company": f"Cloud {i}",
            "location": "Remote",
            "work_mode": "Remote",
            "url": f"https://example.com/devops/{i}",
            "score": 80,
        }
        for i in range(5)
    ]
    db.store_jobs([expired_job] + few_jobs)

    res = db.query_jobs()
    # Expired job must be in closing_soon, NOT in active jobs
    assert len(res["closing_soon"]) == 1
    assert res["closing_soon"][0]["id"] == "old_job"
    assert len(res["jobs"]) == 5

    # Results usable gate: 5 matches < 10 -> too_few
    gate = res["usable_gate"]
    assert gate["usable"] is False
    assert gate["status"] == "too_few"
    assert "below minimum" in gate["message"].lower()
    assert "loosen" in gate["suggestion"].lower()

    # Now add 10 more active jobs -> total 15 matches (within [10, 300])
    more_jobs = [
        {
            "id": f"active_more_{i}",
            "title": f"Platform Engineer {i}",
            "company": f"Infra {i}",
            "location": "Remote",
            "work_mode": "Remote",
            "url": f"https://example.com/platform/{i}",
            "score": 82,
        }
        for i in range(10)
    ]
    db.store_jobs(more_jobs)

    res2 = db.query_jobs()
    assert res2["count"] == 15
    gate2 = res2["usable_gate"]
    assert gate2["usable"] is True
    assert gate2["status"] == "ok"


def test_tombstone_prevents_reinsert(isolated_db):
    job = {
        "id": "tomb_1",
        "title": "Security Analyst",
        "company": "SecureNet",
        "location": "Dallas, TX",
        "work_mode": "Onsite",
        "url": "https://example.com/jobs/sec1",
        "score": 85,
    }
    url_hash = dedup.build_url_hash(job["url"])
    fingerprint = dedup.build_fingerprint(job["company"], job["title"], job["location"], job["work_mode"])

    # Tombstone the hashes
    db.add_tombstone(url_hash, fingerprint)
    assert db.is_tombstoned(url_hash, fingerprint)

    # Ingesting should drop it and return tombstoned status
    res = db.store_jobs([job])
    assert res["tombstoned"] == 1
    assert res["inserted"] == 0

    with db.session() as c:
        row = c.execute("SELECT COUNT(*) FROM jobs WHERE company='SecureNet'").fetchone()[0]
        assert row == 0
