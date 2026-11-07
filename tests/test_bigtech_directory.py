"""Tests for Big Tech Recruiter & Employee Referral Engine."""

from jh import bigtech_directory


def test_list_bigtech_companies():
    companies = bigtech_directory.list_bigtech_companies()
    ids = [c["id"] for c in companies]
    assert "google" in ids
    assert "meta" in ids
    assert "uber" in ids
    assert "amazon" in ids
    assert "apple" in ids
    assert "microsoft" in ids
    assert "netflix" in ids
    assert "stripe" in ids


def test_generate_bigtech_outreach_google():
    profile = {
        "name": "Sarah Connor",
        "target_title": "Full Stack Engineer",
        "skills": ["Python", "React", "PostgreSQL"],
        "experience": [
            {
                "company": "TechCorp",
                "role": "Software Engineer",
                "bullets": ["Architected distributed services and scaled API throughput."],
            }
        ],
        "email": "sarah@example.com",
        "github": "github.com/sarahconnor",
    }
    job = {
        "company": "Google",
        "title": "Software Engineer III",
        "description": "Building high throughput services with Python and PostgreSQL.",
    }

    res = bigtech_directory.generate_bigtech_outreach(
        company_key="google",
        job=job,
        profile=profile,
        recruiter_name="Jennifer Miller",
        req_id="154829",
        leveling_tier="mid",
    )

    assert res["company"] == "Google"
    assert res["level_label"] == "L4"
    assert "Req: 154829" in res["inmail_subject"]
    assert "Hi Jennifer," in res["inmail_body"]
    assert "Candidate: Sarah Connor" in res["referral_blurb"]
    assert "jennifer.miller@google.com" in res["recruiter_email"]
    assert res["inmail_word_count"] < 150
    assert res["review_inmail"]["verdict"].lower() in ("pass", "warn")
    assert res["review_referral"]["verdict"].lower() in ("pass", "warn")


def test_generate_bigtech_outreach_meta_and_uber():
    profile = {
        "name": "Alex Hunter",
        "target_title": "Backend Engineer",
        "skills": ["Go", "Python", "Kubernetes"],
        "experience": [
            {
                "company": "ScaleTech",
                "role": "Backend Engineer",
                "bullets": ["Maintained real-time routing engines with high concurrency."],
            }
        ],
        "email": "alex@example.com",
    }
    job_meta = {"company": "Meta", "title": "Production Engineer"}
    res_meta = bigtech_directory.generate_bigtech_outreach("meta", job_meta, profile, leveling_tier="senior")
    assert res_meta["company"] == "Meta"
    assert res_meta["level_label"] == "E5"
    assert "metacareers.com" in bigtech_directory.BIGTECH_COMPANIES["meta"]["career_portal"]

    job_uber = {"company": "Uber", "title": "Software Engineer II"}
    res_uber = bigtech_directory.generate_bigtech_outreach("uber", job_uber, profile, recruiter_name="David Lee", leveling_tier="mid")
    assert res_uber["company"] == "Uber"
    assert "L4" in res_uber["level_label"]
    assert "david.lee@uber.com" in res_uber["recruiter_email"]
