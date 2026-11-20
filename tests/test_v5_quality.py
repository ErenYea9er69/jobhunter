"""Tests for JobHunter V5: Resume and Application Quality Layer (Checks 1 to 11).

Validates all 12 scripted acceptance checks specified in the V5 requirements:
1) A generated summary has a role and a proof point from facts. Stock phrases are rejected.
2) A bullet with a number not found in facts is blocked or repaired. A bullet with no number is written with no number.
3) A skill not in facts is never added, even when the posting asks for it. It shows as a gap.
4) The PDF round-trip finds sections, email, and phone in order. Under 200 KB.
5) Student / <5 yrs exp gives 1 page; 8 yrs gives at most 2 pages.
6) Proofread gate fails on typos, placeholders, or mismatched company spelling.
7) Anti-slop checks flag stock openers, buzzwords, em dashes, exclamations, and repeated bullet starts.
8) Tailored resume generates in under 5 seconds on Save, and only after Save.
9) Screening questions leave fields empty and flagged when facts are missing.
10) Freshness badge ('posted N hours ago', 'fresh, under 48 hours') and fresh-first sorting.
11) Employment gaps preserve real dates without smoothing or hiding.
"""

import datetime
import io
import os
import time
import pypdf
import pytest

from jh import db, exporters, freshness, home, refit, save_flow, screening, slop, v5_tools


@pytest.fixture
def master_profile():
    return {
        "name": "Alex Mercer",
        "email": "alex.mercer@example.com",
        "phone": "555-019-2831",
        "location": "Austin, TX",
        "target_title": "Senior Backend Engineer",
        "years_of_experience": 4,
        "proof_points": [
            "Scaled payment ingest pipeline to 15,000 req/sec with 99.99% uptime."
        ],
        "skills": ["Python", "PostgreSQL", "FastAPI", "Docker", "Redis", "Kafka"],
        "experience": [
            {
                "company": "Fintech Global",
                "role": "Backend Engineer",
                "dates": "2022-01 - 2024-03",
                "bullets": [
                    "Engineered asynchronous ledger service handling 5,000 tps.",
                    "Optimized database queries reducing p99 latency by 35%.",
                    "Maintained core transaction APIs with FastAPI and PostgreSQL.",
                ],
            },
            {
                "company": "CloudScale Inc",
                "role": "Junior Developer",
                "dates": "2020-03 - 2021-08",
                "bullets": [
                    "Built microservice endpoints in Python and Docker.",
                    "Resolved production bug tickets and drafted test suites.",
                ],
            },
        ],
        "education": [
            {
                "institution": "University of Texas",
                "degree": "B.S. in Computer Science",
                "year": "2020",
            }
        ],
    }


# -----------------------------------------------------------------------------
# Check 1: Summary has role, strength, one proof point; rejects stock phrases
# -----------------------------------------------------------------------------
def test_check_01_summary_role_strength_proof_point(master_profile):
    job = {
        "title": "Senior Backend Engineer",
        "company": "Acme Payments",
        "description": "Looking for Senior Backend Engineer with Python, FastAPI, and Kafka.",
    }
    summary = refit.generate_r3_summary(job, master_profile)
    lines = [line.strip() for line in summary.strip().split("\n") if line.strip()]
    assert len(lines) == 2, f"Summary should be strictly 2 lines, got: {lines}"

    # Line 1: Target role + matching skills
    assert "Senior Backend Engineer" in lines[0] or "Backend Engineer" in lines[0]
    assert any(s in lines[0] for s in ["Python", "FastAPI", "Kafka", "PostgreSQL"])

    # Line 2: One proof point from facts
    assert "15,000 req/sec" in lines[1] or "99.99% uptime" in lines[1]

    # No stock phrases
    stock_phrases = ["hard-working team player", "seeking opportunities", "results-driven", "passionate about", "motivated self-starter"]
    for sp in stock_phrases:
        assert sp not in summary.lower()

    # Verify slop check catches planted stock phrase
    bad_summary = f"{lines[0]}\nResults-driven and passionate about building scalable solutions."
    passed, findings = slop.slop_check(bad_summary, kind="resume")
    assert passed is False
    assert any("stock_phrase" in str(f).lower() for f in findings)


# -----------------------------------------------------------------------------
# Check 2: Metrics - Real numbers only; repair or block; unnumbered kept unnumbered
# -----------------------------------------------------------------------------
def test_check_02_metrics_real_numbers_only(master_profile):
    job = {
        "id": "chk2_job",
        "title": "Backend Engineer",
        "company": "ScaleTech",
        "description": "Python backend engineer.",
    }

    # Bullet with no numbers remains unnumbered
    plain_bullet = "Maintained core transaction APIs with FastAPI and PostgreSQL."
    passed, repaired, findings = save_flow.grounding_check_and_repair(
        f"Professional Experience\nFintech Global\n- {plain_bullet}",
        master_profile,
        job,
        kind="resume",
    )
    assert passed
    assert "Maintained core transaction APIs" in repaired
    # Verify no fake number was inserted
    assert "%" not in repaired and "100" not in repaired

    # Mixed text: fake bullet with fabricated number and valid bullet
    fake_bullet = "Engineered ledger service handling 900,000 req/sec and growing revenue by 85%."
    mixed_text = f"Professional Experience\nFintech Global\n- {fake_bullet}\n- {plain_bullet}"
    passed_mix, repaired_mix, findings_mix = save_flow.grounding_check_and_repair(
        mixed_text,
        master_profile,
        job,
        kind="resume",
    )
    # The repair rounds strip the ungrounded metrics and keep the valid bullet
    assert passed_mix
    assert "900,000" not in repaired_mix
    assert "85%" not in repaired_mix
    assert "Maintained core transaction APIs" in repaired_mix

    # Standalone fake bullet is blocked
    passed_fake, repaired_fake, findings_fake = save_flow.grounding_check_and_repair(
        f"Professional Experience\nFintech Global\n- {fake_bullet}",
        master_profile,
        job,
        kind="resume",
    )
    assert passed_fake is False
    assert any(f.get("code") == "number" for f in findings_fake)

    # Missing metrics question batch (<= 5 questions)
    questions = refit.extract_missing_metric_questions(master_profile, limit=5)
    assert len(questions) <= 5
    assert all("question" in q and "bullet" in q for q in questions)


# -----------------------------------------------------------------------------
# Check 3: Skills not in facts are never added; show as gaps
# -----------------------------------------------------------------------------
def test_check_03_keywords_partition_and_never_fabricate(master_profile):
    posting_text = """
    We need an expert in Python, FastAPI, Docker, and Kubernetes.
    Experience with Rust, Go, and Snowflake is strictly required.
    """
    parts = refit.partition_keywords(posting_text, master_profile)
    assert any("python" in k.lower() for k in parts["have"])
    assert any("fastapi" in k.lower() for k in parts["have"])

    # Candidate does NOT have Rust, Go, or Snowflake
    assert not any("rust" in k.lower() for k in parts["have"])
    assert not any("go" in k.lower() for k in parts["have"])
    assert not any("snowflake" in k.lower() for k in parts["have"])
    assert any("rust" in k.lower() for k in parts["missing"]) or any("go" in k.lower() for k in parts["missing"]) or any("snowflake" in k.lower() for k in parts["missing"])

    # Coverage summary formatted properly
    coverage_text = parts["coverage_text"]
    assert "keyword coverage:" in coverage_text.lower()
    assert "gaps:" in coverage_text.lower()

    # Keyword stuffing check (at most 2 occurrences per term)
    stuffed_text = "Python Python Python and FastAPI FastAPI FastAPI"
    stuff_findings = refit.check_keyword_stuffing(stuffed_text, ["python", "fastapi"])
    assert len(stuff_findings) > 0


# -----------------------------------------------------------------------------
# Check 4: PDF round-trip test; single-column, contact in body, < 200 KB
# -----------------------------------------------------------------------------
def test_check_04_pdf_roundtrip_verification(master_profile):
    pdf_bytes = exporters.to_pdf(master_profile)
    assert len(pdf_bytes) < 200 * 1024  # Under 200 KB

    is_valid, issues = exporters.verify_pdf_roundtrip(pdf_bytes, master_profile)
    assert is_valid, f"Round-trip failed: {issues}"
    assert len(issues) == 0


# -----------------------------------------------------------------------------
# Check 5: Page length: 1 page for <= 5 yrs experience; max 2 pages for senior
# -----------------------------------------------------------------------------
def test_check_05_page_limits(master_profile):
    # Candidate with 4 years experience -> strictly 1 page
    pdf_bytes_junior = exporters.to_pdf(master_profile)
    reader_junior = pypdf.PdfReader(io.BytesIO(pdf_bytes_junior))
    assert len(reader_junior.pages) == 1

    # Senior profile with 8+ years experience -> at most 2 pages
    senior_profile = dict(master_profile)
    senior_profile["years_of_experience"] = 9
    senior_profile["experience"] = master_profile["experience"] * 3  # expand entries
    pdf_bytes_senior = exporters.to_pdf(senior_profile)
    reader_senior = pypdf.PdfReader(io.BytesIO(pdf_bytes_senior))
    assert len(reader_senior.pages) <= 2


# -----------------------------------------------------------------------------
# Check 6: Proofread gate flags typos, placeholders, company name mismatches
# -----------------------------------------------------------------------------
def test_check_06_proofread_gate(master_profile):
    job = {"company": "Acme Corp", "title": "Senior Backend Engineer"}

    # Clean text passes
    clean_text = "Engineered asynchronous ledger service handling 5,000 transactions per second for Acme Corp."
    passed, findings = slop.proofread_gate(clean_text, job, master_profile)
    assert passed is True
    assert len(findings) == 0

    # Planted typo
    typo_text = "Engineered asynchronous ledger service and recievd production traffic."
    passed_typo, typo_findings = slop.proofread_gate(typo_text, job, master_profile)
    assert passed_typo is False
    assert any("typo" in str(f).lower() for f in typo_findings)

    # Planted placeholder
    ph_text = "I am excited to apply for the role at [Company]."
    passed_ph, ph_findings = slop.proofread_gate(ph_text, job, master_profile)
    assert passed_ph is False
    assert any("placeholder" in str(f).lower() for f in ph_findings)

    # Company name misspelling
    wrong_co_text = "I am eager to contribute to Akme Corp."
    passed_co, co_findings = slop.proofread_gate(wrong_co_text, job, master_profile)
    assert passed_co is False
    assert any("company" in str(f).lower() for f in co_findings)


# -----------------------------------------------------------------------------
# Check 7: Slop check flags stock openers, repeated starters, buzzwords
# -----------------------------------------------------------------------------
def test_check_07_slop_check_comprehensive(master_profile):
    # Stock opener
    banned_opener = "I am writing to apply for the Backend Engineer position."
    passed_opener, findings = slop.slop_check(banned_opener, kind="cover_letter")
    assert passed_opener is False
    assert any("banned_opener" in str(f).lower() or "opener" in str(f).lower() for f in findings)

    # Run of bullets starting with the same word
    same_starts = (
        "- Managed cloud infrastructure in AWS.\n"
        "- Managed database migrations with PostgreSQL.\n"
        "- Managed client integrations with REST APIs."
    )
    passed_same, same_findings = slop.slop_check(same_starts, kind="resume")
    assert passed_same is False
    assert any("same_bullet_start" in str(f).lower() or "starter" in str(f).lower() for f in same_findings)

    # Em dash and exclamation marks
    bad_punct = "High performance microservices — scaled to millions! Best in class."
    passed_punct, punct_findings = slop.slop_check(bad_punct, kind="email")
    assert passed_punct is False
    assert any("em dash" in str(f).lower() for f in punct_findings)
    assert any("exclamation" in str(f).lower() for f in punct_findings)


# -----------------------------------------------------------------------------
# Check 8: Tailored resume appears in under 5 seconds, only after Save
# -----------------------------------------------------------------------------
def test_check_08_tailored_resume_speed_and_trigger(master_profile):
    db.save_profile(master_profile)
    job = {
        "id": "job_chk8_perf",
        "title": "Backend Engineer",
        "company": "FastTech Systems",
        "url": "https://example.com/jobs/fasttech",
        "description": "Looking for Backend Engineer with Python, FastAPI, Docker, and PostgreSQL.",
    }
    db.ingest_job(job)

    # Ensure no tailored outputs exist prior to save
    outputs_dir = home.get_home() / "outputs"
    pre_existing = list(outputs_dir.glob("job_chk8_perf*"))
    for f in pre_existing:
        f.unlink()

    # Build base resumes once
    refit.build_role_family_base_resumes(master_profile)

    # Time handle_save_job execution
    start = time.perf_counter()
    res = save_flow.handle_save_job("job_chk8_perf", force=True)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"Generation took {elapsed:.2f}s, expected < 5.0s"
    assert res.get("status") in ("ok", "ready", "success", "approved")
    # Verify file was generated after save
    created_files = list(outputs_dir.glob("job_chk8_perf*"))
    assert len(created_files) > 0


# -----------------------------------------------------------------------------
# Check 9: Screening questions leave field empty and flagged if fact missing
# -----------------------------------------------------------------------------
def test_check_09_screening_empty_when_fact_missing(master_profile):
    # Question on a fact candidate has: years of experience
    ans_known = screening.answer_screening_question(
        "How many years of backend experience do you have?",
        master_profile,
    )
    assert "4" in ans_known["answer"]
    assert not ans_known["flagged"]

    # Question on unknown fact: security clearance
    ans_missing = screening.answer_screening_question(
        "What is your active United States Department of Defense security clearance level?",
        master_profile,
    )
    # R8: If fact is missing, leave the field empty and flag it. Never invent.
    assert ans_missing["answer"] == ""
    assert ans_missing["flagged"] is True


# -----------------------------------------------------------------------------
# Check 10: Freshness age, fresh badge, and fresh-first sorting
# -----------------------------------------------------------------------------
def test_check_10_freshness_badge_and_sorting():
    now = datetime.datetime.now(datetime.timezone.utc)
    fresh_time = (now - datetime.timedelta(hours=6)).isoformat()
    older_time = (now - datetime.timedelta(hours=96)).isoformat()

    fresh_job = {
        "id": "job_fresh_10",
        "title": "Cloud Architect",
        "company": "FreshCorp",
        "posted_at": fresh_time,
        "score": 85,
    }
    older_job = {
        "id": "job_older_10",
        "title": "Cloud Architect",
        "company": "OlderCorp",
        "posted_at": older_time,
        "score": 95,  # Higher score, but older
    }

    # Freshness calculation
    assert freshness.is_fresh_48h(fresh_job) is True
    assert freshness.is_fresh_48h(older_job) is False

    fresh_badge = freshness.format_freshness_badge(fresh_job)
    assert fresh_badge["is_fresh"] is True
    assert fresh_badge["badge"] == "fresh, under 48 hours"
    assert "posted 6 hours ago" in fresh_badge["label"]

    older_badge = freshness.format_freshness_badge(older_job)
    assert older_badge["is_fresh"] is False
    assert older_badge["badge"] is None
    assert "posted 96 hours ago" in older_badge["label"]

    # Ingest and query to test fresh-first sorting
    db.ingest_job(fresh_job)
    db.ingest_job(older_job)
    res = db.query_jobs()
    matching_ids = [j["id"] for j in res.get("jobs", [])]
    if "job_fresh_10" in matching_ids and "job_older_10" in matching_ids:
        fresh_idx = matching_ids.index("job_fresh_10")
        older_idx = matching_ids.index("job_older_10")
        assert fresh_idx < older_idx, "Fresh jobs must sort before older jobs in filtered matches"


# -----------------------------------------------------------------------------
# Check 11: Employment gaps keep real dates without smoothing or hiding
# -----------------------------------------------------------------------------
def test_check_11_employment_gap_preserves_real_dates():
    profile_with_gap = {
        "name": "Jordan Lee",
        "email": "jordan@example.com",
        "phone": "555-432-1098",
        "target_title": "Software Engineer",
        "years_of_experience": 3,
        "experience": [
            {
                "company": "Alpha Tech",
                "role": "Frontend Developer",
                "dates": "2020-01 - 2020-08",
                "bullets": ["Developed user interfaces with React."],
            },
            # Gap of 14 months between 2020-08 and 2021-10
            {
                "company": "Beta Cloud",
                "role": "Software Engineer",
                "dates": "2021-10 - 2023-05",
                "bullets": ["Maintained backend services in Python."],
            },
        ],
        "education": [],
        "skills": ["React", "Python"],
    }
    job = {"title": "Software Engineer", "company": "Gamma Systems", "description": "Software engineer."}
    tailored = refit.tailor_base_resume(profile_with_gap, job)

    exps = tailored.get("experience", [])
    assert len(exps) == 2
    dates_found = [e.get("dates") for e in exps]
    # R1: Never hide or smooth an employment gap or a layoff. Keep the real dates.
    assert "2020-01 - 2020-08" in dates_found
    assert "2021-10 - 2023-05" in dates_found
